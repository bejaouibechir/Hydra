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
