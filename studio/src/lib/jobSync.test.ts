import { describe, expect, it } from 'vitest'
import { canonicalFromCanvas, canvasFromDisk, decideSync } from './jobSync'

describe('decideSync — la dernière modification gagne', () => {
  const base = { same: false, diskChanged: false, studioEditAt: null as number | null, diskMtimeMs: 1000 }
  it('même contenu : rien à faire', () => {
    expect(decideSync({ ...base, same: true, diskChanged: true, studioEditAt: 5 })).toBe('in_sync')
  })
  it('seul le disque a changé : relire le disque', () => {
    expect(decideSync({ ...base, diskChanged: true })).toBe('load_disk')
  })
  it('rien de neuf des deux côtés (forme différente) : ne pas boucler', () => {
    expect(decideSync(base)).toBe('in_sync')
  })
  it('seul Studio a changé : écrire sur le disque', () => {
    expect(decideSync({ ...base, studioEditAt: 2000 })).toBe('save_studio')
  })
  it('les deux ont changé : la date la plus récente gagne', () => {
    expect(decideSync({ ...base, diskChanged: true, studioEditAt: 2000, diskMtimeMs: 3000 })).toBe('load_disk')
    expect(decideSync({ ...base, diskChanged: true, studioEditAt: 4000, diskMtimeMs: 3000 })).toBe('save_studio')
  })
})

describe('forme canonique', () => {
  const files = {
    sources: '# commentaire\nsources:\n  src_csv:\n    type: csv\n    extract:\n      table: data/input.csv\n      batch_size: 7000\n',
    transformations: 'steps: []\n',
    destinations: 'destinations:\n  dest_csv:\n    type: csv\n    load:\n      table: data/output.csv\n      mode: replace\n',
    pipeline: 'pipeline:\n  from: src_csv\n  to: dest_csv\n',
  }
  it('le canvas relu du disque est identique au disque (pas de faux changement)', () => {
    const d = canvasFromDisk(files, 'job1')!
    const again = canvasFromDisk({ ...files, sources: files.sources.replace('# commentaire\n', '') }, 'job1')!
    expect(canonicalFromCanvas(d.nodes, d.edges, 'job1')).toBe(canonicalFromCanvas(again.nodes, again.edges, 'job1'))
  })
  it('un changement de valeur sur le disque change la forme canonique', () => {
    const a = canvasFromDisk(files, 'job1')!
    const b = canvasFromDisk({ ...files, sources: files.sources.replace('7000', '5000') }, 'job1')!
    expect(canonicalFromCanvas(a.nodes, a.edges, 'job1')).not.toBe(canonicalFromCanvas(b.nodes, b.edges, 'job1'))
    expect(canonicalFromCanvas(b.nodes, b.edges, 'job1')).toContain('batch_size: 5000')
  })
  it('YAML vide : null', () => {
    expect(canvasFromDisk({ sources: '', transformations: '', destinations: '', pipeline: '' }, 'j')).toBeNull()
  })
})

describe('load.atomic (tout ou rien) d\'une destination base', () => {
  const pg = (extra: string) => ({
    sources: 'sources:\n  src_csv:\n    type: csv\n    extract:\n      table: data/input.csv\n      batch_size: 7000\n',
    transformations: 'steps: []\n',
    destinations: 'destinations:\n  dest_pg:\n    type: postgresql\n    connection:\n      host: h\n      database: d\n      user: u\n'
      + '    load:\n      table: t\n      mode: append\n' + extra,
    pipeline: 'pipeline:\n  from: src_csv\n  to: dest_pg\n',
  })
  it('lu du disque, gardé à l\'écriture ; absent = défaut', () => {
    for (const [extra, want] of [['      atomic: true\n', 'atomic: true'], ['      atomic: false\n', 'atomic: false']] as const) {
      const d = canvasFromDisk(pg(extra), 'job1')!
      const dest = d.nodes.find(n => (n.data as { params?: Record<string, unknown> }).params?.atomic !== undefined)!
      expect((dest.data as { params: Record<string, unknown> }).params.atomic).toBe(extra.includes('true') ? 'yes' : 'no')
      expect(canonicalFromCanvas(d.nodes, d.edges, 'job1')).toContain(want)
    }
    const d = canvasFromDisk(pg(''), 'job1')!
    expect(canonicalFromCanvas(d.nodes, d.edges, 'job1')).not.toContain('atomic')
  })
})


describe('transformations.yaml avec steps à la racine (hdrctl init, CLI)', () => {
  it('les opérations sont lues et réécrites, jamais perdues', () => {
    const files = {
      sources: 'sources:\n  src:\n    type: csv\n    extract:\n      table: ../../Data/orders.csv\n',
      transformations: 'version: "1.0"\nsteps:\n  - cast:\n      mapping:\n        amount: float\n'
        + '  - aggregate:\n      by: [customer]\n      agg:\n        total: { func: sum, col: amount }\n',
      destinations: 'destinations:\n  dst:\n    type: csv\n    load:\n      table: ../../outputs/report.csv\n      mode: replace\n',
      pipeline: 'pipeline:\n  from: src\n  to: dst\n',
    }
    const d = canvasFromDisk(files, 'build_report')!
    const out = canonicalFromCanvas(d.nodes, d.edges, 'build_report')
    expect(out).toContain('cast')
    expect(out).toContain('aggregate')
    expect(out).toContain('amount: float')
    expect(out).toMatch(/func: sum/)
    expect(out).toMatch(/col: amount/)
    expect(out).toMatch(/customer/)
  })
})
