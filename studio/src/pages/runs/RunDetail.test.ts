import { describe, expect, it } from 'vitest'
import { fmtWait } from './RunDetail'

describe('fmtWait', () => {
  it('rend une attente lisible', () => {
    expect(fmtWait(0.5)).toBe('500ms')
    expect(fmtWait(23)).toBe('23s')
    expect(fmtWait(300)).toBe('5m')
    expect(fmtWait(3600)).toBe('1h')
    expect(fmtWait(90)).toBe('90s')
  })
})
