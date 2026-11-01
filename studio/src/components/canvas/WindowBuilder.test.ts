import { describe, it, expect } from 'vitest'
import { parseWindowColumns, serializeWindowColumns } from './WindowBuilder'

describe('WindowBuilder — JSON columns', () => {
  it('aller-retour : options gardées selon la fonction, valeurs typées', () => {
    const json = JSON.stringify({
      rn: { func: 'row_number' },
      prev: { func: 'lag', col: 'amount', offset: 2, default: 0 },
      nxt: { func: 'lead', col: 'city', default: 'none' },
      run: { func: 'cumsum', col: 'amount' },
      n: { func: 'cumcount' },
    })
    expect(JSON.parse(serializeWindowColumns(parseWindowColumns(json)))).toEqual(JSON.parse(json))
  })

  it('une colonne ou un décalage saisis pour une fonction qui ne les prend pas sont écartés', () => {
    const rows = parseWindowColumns(JSON.stringify({ r: { func: 'rank' } }))
    rows[0].col = 'amount'; rows[0].offset = '3'; rows[0].def = '1'
    expect(JSON.parse(serializeWindowColumns(rows))).toEqual({ r: { func: 'rank' } })
  })

  it('lignes sans nom ignorées ; JSON invalide -> aucune ligne', () => {
    const rows = parseWindowColumns('{"a": {"func": "sum", "col": "x"}}')
    rows.push({ ...rows[0], _id: 999, out: '  ' })
    expect(serializeWindowColumns(rows)).toBe('{"a":{"func":"sum","col":"x"}}')
    expect(parseWindowColumns('{oops')).toEqual([])
  })
})
