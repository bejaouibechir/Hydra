import { describe, expect, it } from 'vitest'
import { Briefcase, Package } from 'lucide-react'
import { getAllNodes } from './nodeRegistry'
import { CATEGORY_COLORS, JOB_COLOR, nodeAppearance, resolveIcon } from './nodeAppearance'

describe('nodeAppearance — canvas node = palette item', () => {
  it('every palette node has a known icon (no fallback)', () => {
    const missing = getAllNodes().filter(n => resolveIcon(n.icon) === Briefcase).map(n => `${n.type}:${n.icon}`)
    expect(missing).toEqual([])
  })

  it('canvas color and icon are those of the palette', () => {
    for (const n of getAllNodes().filter(n => n.type !== 'job')) {
      const a = nodeAppearance(n.type)
      expect(a.color, n.type).toBe(CATEGORY_COLORS[n.category])
      expect(a.Icon, n.type).toBe(resolveIcon(n.icon))
    }
  })

  it('sources are green, destinations orange, jobs violet', () => {
    expect(nodeAppearance('source_postgres').color).toBe('var(--success)')
    expect(nodeAppearance('dest_json').color).toBe('var(--warning)')
    expect(nodeAppearance('job')).toMatchObject({ Icon: Package, color: JOB_COLOR })
    expect(nodeAppearance('action_webhook').Icon).toBe(resolveIcon('Webhook'))
  })
})
