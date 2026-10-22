/**
 * lib/thread.ts — Opérations pures sur workflows/thread.yaml côté Studio.
 * Même modèle que hydra_etl/workflow/thread.py : des étapes (stages) lancées
 * l'une après l'autre, chacune sequential ou parallel, avec un délai optionnel
 * et des workflows actifs ou non.
 */
export interface ThreadWorkflow { name: string; active: boolean }
export interface ThreadStage {
  mode: 'sequential' | 'parallel'
  delay_after?: string | number | null
  workflows: ThreadWorkflow[]
}

const clone = (s: ThreadStage[]): ThreadStage[] =>
  s.map(st => ({ ...st, workflows: st.workflows.map(w => ({ ...w })) }))

/** Déplace un workflow d'un cran (dir = -1 haut, +1 bas), en passant d'une étape à l'autre. */
export function moveWorkflow(stages: ThreadStage[], si: number, wi: number, dir: -1 | 1): ThreadStage[] {
  const out = clone(stages)
  const st = out[si]
  if (!st || !st.workflows[wi]) return out
  const ws = st.workflows
  if (dir === -1) {
    if (wi > 0) { [ws[wi - 1], ws[wi]] = [ws[wi], ws[wi - 1]]; return out }
    if (si === 0) return out
    const [w] = ws.splice(wi, 1)
    out[si - 1].workflows.push(w)
    return out
  }
  if (wi < ws.length - 1) { [ws[wi + 1], ws[wi]] = [ws[wi], ws[wi + 1]]; return out }
  if (si === out.length - 1) return out
  const [w] = ws.splice(wi, 1)
  out[si + 1].workflows.unshift(w)
  return out
}

/** Ajoute un workflow en fin de thread (dernière étape si séquentielle, sinon nouvelle étape). */
export function appendWorkflow(stages: ThreadStage[], name: string): ThreadStage[] {
  const out = clone(stages)
  const last = out[out.length - 1]
  if (last && last.mode === 'sequential') last.workflows.push({ name, active: true })
  else out.push({ mode: 'sequential', workflows: [{ name, active: true }] })
  return out
}

export function removeWorkflow(stages: ThreadStage[], si: number, wi: number): ThreadStage[] {
  const out = clone(stages)
  out[si]?.workflows.splice(wi, 1)
  return out
}

/** Étapes vides retirées, délai vide supprimé : ce qu'on envoie à l'API. */
export function forSave(stages: ThreadStage[]): ThreadStage[] {
  return clone(stages)
    .filter(st => st.workflows.length > 0)
    .map(st => {
      const d = typeof st.delay_after === 'string' ? st.delay_after.trim() : st.delay_after
      const out: ThreadStage = { mode: st.mode, workflows: st.workflows }
      if (d !== undefined && d !== null && d !== '' && d !== 0) out.delay_after = d
      return out
    })
}

export function namesIn(stages: ThreadStage[]): string[] {
  return stages.flatMap(st => st.workflows.map(w => w.name))
}

const DELAY_RE = /^\s*\d+(\.\d+)?\s*(ms|s|m|h)?\s*$/i
export const isValidDelay = (v: string | number | null | undefined) =>
  v === undefined || v === null || v === '' || typeof v === 'number' || DELAY_RE.test(v)

// ── Boucles ─────────────────────────────────────────────────────────────────
/** Boucle : rejouer la portion du thread qui va de `to` à `from`, `times` fois en tout. */
export interface ThreadLoop { from: string; to: string; times: number; delay?: string | number | null }

export const MAX_LOOP_TIMES = 1000

/** Unités d'exécution, comme ThreadDef.units() côté Python : un workflow d'une
 *  étape séquentielle, ou une étape parallèle entière. */
export interface ThreadUnit { stage: number; names: string[]; parallel: boolean; lastInStage: boolean }

export function threadUnits(stages: ThreadStage[]): ThreadUnit[] {
  const out: ThreadUnit[] = []
  stages.forEach((st, si) => {
    if (st.workflows.length === 0) return
    if (st.mode === 'parallel') {
      out.push({ stage: si, names: st.workflows.map(w => w.name), parallel: true, lastInStage: true })
    } else {
      st.workflows.forEach((w, i) => out.push({
        stage: si, names: [w.name], parallel: false, lastInStage: i === st.workflows.length - 1,
      }))
    }
  })
  return out
}

export function unitOf(units: ThreadUnit[], name: string): number {
  return units.findIndex(u => u.names.includes(name))
}

/** Mêmes règles que le moteur : un message par boucle invalide (null si valide). */
export function loopErrors(stages: ThreadStage[], loops: ThreadLoop[]): (string | null)[] {
  const units = threadUnits(stages)
  const spans: [number, number][] = []
  return loops.map(lp => {
    const a = unitOf(units, lp.to), b = unitOf(units, lp.from)
    if (a < 0 || b < 0) return `'${a < 0 ? lp.to : lp.from}' is not in the thread`
    if (a > b) return `'${lp.to}' must come before '${lp.from}' (a loop goes back)`
    if (!Number.isInteger(lp.times) || lp.times < 1 || lp.times > MAX_LOOP_TIMES) return `times: 1 to ${MAX_LOOP_TIMES}`
    if (!isValidDelay(lp.delay ?? '')) return 'invalid delay (use 30s, 5m, 1h)'
    if (spans.some(([a2, b2]) => !(b < a2 || b2 < a))) return 'overlaps another loop'
    spans.push([a, b])
    return null
  })
}

/** Boucles prêtes à l'envoi : délai vide retiré. */
export function loopsForSave(loops: ThreadLoop[]): ThreadLoop[] {
  return loops.map(lp => {
    const d = typeof lp.delay === 'string' ? lp.delay.trim() : lp.delay
    const out: ThreadLoop = { from: lp.from, to: lp.to, times: Number(lp.times) }
    if (d !== undefined && d !== null && d !== '' && d !== 0) out.delay = d
    return out
  })
}

/** Retire les boucles qui citent un workflow sorti du thread. */
export function pruneLoops(stages: ThreadStage[], loops: ThreadLoop[]): ThreadLoop[] {
  const names = new Set(namesIn(stages))
  return loops.filter(lp => names.has(lp.from) && names.has(lp.to))
}
