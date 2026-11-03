/**
 * lib/triggers.ts — déclencheurs de projet (triggers.yaml, Hydra 0.19) côté Studio.
 *
 * Fonctions pures : métadonnées des sept types (libellé, couleur, clés), passage
 * entre la config écrite dans triggers.yaml et le formulaire de l'onglet Triggers,
 * et contrôles immédiats. Le serveur revalide tout (PUT /projects/{id}/triggers).
 */

export type TriggerType = 'cron' | 'interval' | 'file' | 'marker' | 'source_change' | 'webhook' | 'after_project'

export const TRIGGER_TYPES: { id: TriggerType; label: string; color: string; hint: string }[] = [
  { id: 'cron', label: 'At given times', color: '#f59e0b', hint: 'cron expression, e.g. every night at 02:00' },
  { id: 'interval', label: 'Every N minutes', color: '#eab308', hint: 'a regular period' },
  { id: 'file', label: 'A file arrives', color: '#22c55e', hint: 'a file matching a path is added or modified' },
  { id: 'marker', label: 'A marker file appears', color: '#10b981', hint: 'e.g. inbox/READY, removed before the run' },
  { id: 'source_change', label: 'A source changes', color: '#3b82f6', hint: 'count, max of a column or checksum of a source' },
  { id: 'webhook', label: 'An HTTP call', color: '#a855f7', hint: 'another system calls Hydra with a token' },
  { id: 'after_project', label: 'Another project ends', color: '#14b8a6', hint: 'success, failure or any end' },
]
export const typeMeta = (t: string) => TRIGGER_TYPES.find(x => x.id === t) ?? TRIGGER_TYPES[0]

export const CRON_PRESETS: { cron: string; label: string }[] = [
  { cron: '0 2 * * *', label: 'every night at 02:00' },
  { cron: '0 8 * * mon-fri', label: 'weekdays at 08:00' },
  { cron: '*/15 * * * *', label: 'every 15 minutes' },
  { cron: '0 * * * *', label: 'every hour' },
  { cron: '0 6 1 * *', label: 'the 1st of the month at 06:00' },
]

/** Config telle qu'écrite dans triggers.yaml (renvoyée par l'API dans `config`). */
export type TriggerConfig = Record<string, unknown> & { name: string; type: TriggerType }

/** État du formulaire : tout en texte, plus simple à éditer. */
export interface TriggerForm {
  name: string; type: TriggerType; description: string; enabled: boolean
  cron: string; timezone: string; every: string
  path: string; events: ('added' | 'modified')[]; debounce: string; consume: boolean
  sourceJob: string; sourceId: string; sourceCheck: 'count' | 'max' | 'checksum'; sourceColumn: string
  token: string; project: string; ref: 'path' | 'name'; on: 'success' | 'failure' | 'any'
  env: string; workflows: string[]; params: { key: string; value: string }[]
  overlap: 'skip' | 'wait' | 'fail'; timeout: string; retryMax: string; retryDelay: string
}

export const tokenRef = (name: string) => '${SECRET:trigger.' + (name || 'name') + '.token}'

export function emptyForm(type: TriggerType = 'cron', name = ''): TriggerForm {
  return {
    name, type, description: '', enabled: true,
    cron: '0 2 * * *', timezone: '', every: type === 'interval' ? '15m' : '',
    path: type === 'marker' ? 'inbox/READY' : type === 'file' ? 'inbox/*.csv' : '', events: ['added'], debounce: '', consume: true,
    sourceJob: '', sourceId: '', sourceCheck: 'count', sourceColumn: '',
    token: tokenRef(name), project: '', ref: 'path', on: 'success',
    env: '', workflows: [], params: [], overlap: 'skip', timeout: '', retryMax: '', retryDelay: '',
  }
}

const str = (v: unknown) => (v == null ? '' : String(v))

export function formFromConfig(c: TriggerConfig): TriggerForm {
  const f = emptyForm(c.type, c.name)
  const src = (c.source ?? {}) as Record<string, unknown>
  const retry = (c.retry ?? {}) as Record<string, unknown>
  return {
    ...f,
    description: str(c.description), enabled: c.enabled !== false,
    cron: c.type === 'cron' ? str(c.cron) : f.cron, timezone: str(c.timezone), every: str(c.every),
    path: c.path != null ? str(c.path) : f.path,
    events: Array.isArray(c.events) ? (c.events as TriggerForm['events']) : ['added'],
    debounce: str(c.debounce), consume: c.consume !== false,
    sourceJob: str(src.job), sourceId: str(src.id),
    sourceCheck: (src.check as TriggerForm['sourceCheck']) ?? 'count', sourceColumn: str(src.column),
    token: c.token != null ? str(c.token) : f.token,
    project: str(c.project), ref: (c.ref as TriggerForm['ref']) ?? 'path', on: (c.on as TriggerForm['on']) ?? 'success',
    env: str(c.env), workflows: Array.isArray(c.workflows) ? c.workflows.map(String) : [],
    params: Object.entries((c.params ?? {}) as Record<string, unknown>).map(([key, value]) => ({ key, value: str(value) })),
    overlap: (c.overlap as TriggerForm['overlap']) ?? 'skip', timeout: str(c.timeout),
    retryMax: retry.max != null ? str(retry.max) : '', retryDelay: str(retry.delay),
  }
}

/** Formulaire → config de triggers.yaml : seulement les clés du type, sans les valeurs par défaut. */
export function configFromForm(f: TriggerForm): TriggerConfig {
  const c: TriggerConfig = { name: f.name.trim(), type: f.type }
  if (f.description.trim()) c.description = f.description.trim()
  if (!f.enabled) c.enabled = false
  const t = f.type
  if (t === 'cron') { c.cron = f.cron.trim(); if (f.timezone.trim()) c.timezone = f.timezone.trim() }
  if (t === 'interval') c.every = f.every.trim()
  if (t === 'file' || t === 'marker') {
    c.path = f.path.trim()
    if (t === 'file') {
      if (!(f.events.length === 1 && f.events[0] === 'added')) c.events = f.events
      if (f.debounce.trim()) c.debounce = f.debounce.trim()
    }
    if (t === 'marker' && !f.consume) c.consume = false
  }
  if ((t === 'file' || t === 'marker' || t === 'source_change') && f.every.trim()) c.every = f.every.trim()
  if (t === 'source_change') {
    const s: Record<string, unknown> = { job: f.sourceJob.trim(), id: f.sourceId.trim() }
    if (f.sourceCheck !== 'count') s.check = f.sourceCheck
    if (f.sourceCheck === 'max') s.column = f.sourceColumn.trim()
    c.source = s
  }
  if (t === 'webhook') c.token = f.token.trim() || tokenRef(f.name.trim())
  if (t === 'after_project') {
    c.project = f.project.trim()
    if (f.ref !== 'path') c.ref = f.ref
    if (f.on !== 'success') c.on = f.on
  }
  if (f.env.trim()) c.env = f.env.trim()
  if (f.workflows.length) c.workflows = f.workflows
  const params = Object.fromEntries(f.params.filter(p => p.key.trim()).map(p => [p.key.trim(), p.value]))
  if (Object.keys(params).length) c.params = params
  if (f.overlap !== 'skip') c.overlap = f.overlap
  if (f.timeout.trim()) c.timeout = f.timeout.trim()
  if (f.retryMax.trim()) {
    const r: Record<string, unknown> = { max: Number(f.retryMax) }
    if (f.retryDelay.trim()) r.delay = f.retryDelay.trim()
    c.retry = r
  }
  return c
}

const NAME_RE = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/
const DELAY_RE = /^\s*\d+(\.\d+)?\s*(ms|s|m|h)?\s*$/i

/** Problèmes visibles avant d'enregistrer (le serveur fait le contrôle complet). */
export function formProblems(f: TriggerForm, otherNames: string[]): string[] {
  const out: string[] = []
  const n = f.name.trim()
  if (!n) out.push('A name is required.')
  else if (!NAME_RE.test(n)) out.push("Name: letters, digits, '.', '_' or '-'.")
  else if (otherNames.includes(n)) out.push(`The name '${n}' is already used.`)
  const delay = (v: string, what: string, required = false) => {
    if (!v.trim()) { if (required) out.push(`${what} is required.`); return }
    if (!DELAY_RE.test(v)) out.push(`${what}: a number of seconds, or 30s, 5m, 1h.`)
  }
  if (f.type === 'cron' && f.cron.trim().split(/\s+/).length !== 5) out.push('Cron: five fields (minute hour day month weekday).')
  if (f.type === 'interval') delay(f.every, 'Every', true)
  else delay(f.every, 'Check every')
  if (f.type === 'file' || f.type === 'marker') {
    const p = f.path.trim().replace(/\\/g, '/')
    if (!p) out.push('A path is required.')
    else if (p.startsWith('/') || /^[A-Za-z]:/.test(p) || p.split('/').includes('..')) out.push('The path must stay inside the project.')
    if (f.type === 'file' && f.events.length === 0) out.push('Choose at least one event.')
  }
  delay(f.debounce, 'Debounce')
  if (f.type === 'source_change') {
    if (!f.sourceJob.trim() || !f.sourceId.trim()) out.push('Choose the job and the source.')
    if (f.sourceCheck === 'max' && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(f.sourceColumn.trim())) out.push('Max: give a column name.')
  }
  if (f.type === 'webhook' && !/^\$\{SECRET:[A-Za-z0-9_.-]+\}$/.test(f.token.trim())) out.push('Token: a ${SECRET:name} reference.')
  if (f.type === 'after_project' && !f.project.trim()) out.push('Choose the project.')
  delay(f.timeout, 'Timeout')
  if (f.retryMax.trim() && !(/^\d+$/.test(f.retryMax) && +f.retryMax >= 1 && +f.retryMax <= 10)) out.push('Retries: 1 to 10.')
  delay(f.retryDelay, 'Retry delay')
  if (f.params.some(p => p.value.includes('${SECRET:'))) out.push('No secret in parameters: the project reads its own secrets.')
  return out
}
