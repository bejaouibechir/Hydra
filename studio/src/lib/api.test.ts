import { describe, it, expect } from 'vitest'
import { ApiError, conflictFiles } from './api'

describe('ApiError / conflictFiles', () => {
  it('garde le statut et un message lisible', () => {
    expect(new ApiError(404, "Workflow 'x' not found").message).toBe("Workflow 'x' not found")
    const e = new ApiError(409, { message: 'Files changed outside Studio since the last save', files: ['workflows/a.yaml'] })
    expect(e.status).toBe(409)
    expect(e.message).toBe('Files changed outside Studio since the last save')
  })

  it('extrait les fichiers en conflit d\'un 409 seulement', () => {
    expect(conflictFiles(new ApiError(409, { files: ['workflows/a.yaml', 'jobs/j/sources.yaml'] })))
      .toEqual(['workflows/a.yaml', 'jobs/j/sources.yaml'])
    expect(conflictFiles(new ApiError(409, 'conflict'))).toEqual([])
    expect(conflictFiles(new ApiError(500, { files: ['x'] }))).toBeNull()
    expect(conflictFiles(new Error('network'))).toBeNull()
  })
})
