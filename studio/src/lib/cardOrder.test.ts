import { describe, expect, it } from 'vitest'
import { moveTo, sortByIds, swap } from './cardOrder'

describe('moveTo', () => {
  it('moves forward and backward', () => {
    expect(moveTo(['a', 'b', 'c', 'd'], 'd', 'a')).toEqual(['d', 'a', 'b', 'c'])
    expect(moveTo(['a', 'b', 'c', 'd'], 'a', 'c')).toEqual(['b', 'c', 'a', 'd'])
    expect(moveTo(['a', 'b', 'c'], 'b', 'c')).toEqual(['a', 'c', 'b'])
  })
  it('ignores unknown ids and self drops', () => {
    const ids = ['a', 'b']
    expect(moveTo(ids, 'a', 'a')).toBe(ids)
    expect(moveTo(ids, 'x', 'a')).toBe(ids)
  })
})

describe('swap', () => {
  it('exchanges the two cards only', () => {
    expect(swap(['a', 'b', 'c', 'd'], 'd', 'a')).toEqual(['d', 'b', 'c', 'a'])
    expect(swap(['a', 'b', 'c'], 'a', 'b')).toEqual(['b', 'a', 'c'])
  })
  it('ignores unknown ids and self drops', () => {
    const ids = ['a', 'b']
    expect(swap(ids, 'a', 'a')).toBe(ids)
    expect(swap(ids, 'x', 'a')).toBe(ids)
  })
})

describe('sortByIds', () => {
  it('puts unknown items last, in their order', () => {
    const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]
    expect(sortByIds(items, ['c', 'a']).map(i => i.id)).toEqual(['c', 'a', 'b', 'd'])
  })
})
