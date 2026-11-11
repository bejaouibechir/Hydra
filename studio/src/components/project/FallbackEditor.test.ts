import { describe, it, expect } from 'vitest'
import { conditionPart } from './FallbackEditor'

describe('conditionPart (assistant de condition)', () => {
  it('fonctions booléennes, avec ou sans not', () => {
    expect(conditionPart('source_available', 'bool', 'crm', true, '<', '')).toBe("not source_available('crm')")
    expect(conditionPart('url_ok', 'bool', "http://x/a'b", false, '<', '')).toBe("url_ok('http://x/a\\'b')")
  })
  it('fonctions mesurées : comparaison et valeur par défaut', () => {
    expect(conditionPart('file_size', 'bytes', 'in.csv', true, '<', '')).toBe("file_size('in.csv') < 1MB")
    expect(conditionPart('file_age', 'seconds', 'in.csv', false, '>', '2h')).toBe("file_age('in.csv') > 2h")
  })
  it('fonctions texte (cdc.slot_status) : valeur entre guillemets, == ou != seulement', () => {
    expect(conditionPart('cdc.slot_status', 'text', 'orders', false, '==', '')).toBe("cdc.slot_status('orders') == 'lost'")
    expect(conditionPart('cdc.slot_status', 'text', 'orders', false, '!=', 'reserved')).toBe("cdc.slot_status('orders') != 'reserved'")
    expect(conditionPart('cdc.slot_lag', 'bytes', 'orders', false, '>', '2GB')).toBe("cdc.slot_lag('orders') > 2GB")
  })
  it('valeurs previous.*', () => {
    expect(conditionPart('previous.status', 'attr', '', false, '==', '')).toBe("previous.status == 'failed'")
    expect(conditionPart('previous.rows', 'attr', '', false, '<', '100')).toBe('previous.rows < 100')
  })
})

describe('undo d\'une action (NodeConfigDialog)', () => {
  it('valeur enregistrée et champs', async () => {
    const { undoValue, undoFields } = await import('../canvas/NodeConfigDialog')
    expect(undoValue('unset', {})).toBeUndefined()
    expect(undoValue('none', { x: '1' })).toBe('none')
    expect(undoValue('bash', { command: 'rm f', timeout: '' })).toEqual({ action: 'bash', params: { command: 'rm f' } })
    expect(undoFields('bash').map(f => f.key)).toContain('command')
    expect(undoFields('python').map(f => f.key)).toEqual(['script', 'file_path'])
  })
})
