/**
 * FolderPicker — explorateur de dossiers/fichiers 100 % web.
 *
 * Remplace le dialogue natif côté serveur (api.system.browse) qui ne peut pas
 * s'afficher quand le backend tourne sans display (WSL, Docker, serveur distant).
 *
 * Usage impératif, compatible avec l'ancien code :
 *   const res = await pickPath('directory')       // { path: string | null }
 *   const res = await pickPath('file', '.csv')
 *
 * Requiert que <FolderPickerHost /> soit monté une fois à la racine de l'app.
 */
import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { Folder, FileText, CornerLeftUp, HardDrive, X, Check, Loader2 } from 'lucide-react'

type PickType = 'file' | 'directory' | 'save_file'
interface PickResult { path: string | null }
interface PickOpts { type: PickType; ext: string }

// ── Pont impératif ──────────────────────────────────────────────────────────
let _openImpl: ((opts: PickOpts) => Promise<PickResult>) | null = null

export function pickPath(type: PickType, ext = ''): Promise<PickResult> {
  if (_openImpl) return _openImpl({ type, ext })
  // Filet de sécurité : si le host n'est pas monté, retomber sur le natif.
  return api.system.browse(type, ext)
}

// ── Host à monter une seule fois ─────────────────────────────────────────────
export function FolderPickerHost() {
  const [req, setReq] = useState<{ opts: PickOpts; resolve: (r: PickResult) => void } | null>(null)

  useEffect(() => {
    _openImpl = (opts) => new Promise<PickResult>((resolve) => setReq({ opts, resolve }))
    return () => { _openImpl = null }
  }, [])

  if (!req) return null
  const finish = (path: string | null) => { req.resolve({ path }); setReq(null) }
  return <PickerModal opts={req.opts} onFinish={finish} />
}

// ── Modal de navigation ──────────────────────────────────────────────────────
interface Entry { name: string; path: string; is_dir: boolean }

function PickerModal({ opts, onFinish }: { opts: PickOpts; onFinish: (p: string | null) => void }) {
  const dirMode = opts.type === 'directory'
  const [cwd, setCwd] = useState<string | null>(null)          // null = vue racines
  const [parent, setParent] = useState<string | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [roots, setRoots] = useState<Entry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [manual, setManual] = useState('')

  const loadRoots = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await api.system.fsRoots()
      setRoots(r.roots.map(x => ({ ...x, is_dir: true })))
      setCwd(null); setParent(null); setEntries([])
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }, [])

  const openDir = useCallback(async (path: string) => {
    setLoading(true); setError(null)
    try {
      const r = await api.system.fsList(path, dirMode, opts.ext)
      setCwd(r.path); setParent(r.parent); setEntries(r.entries); setManual(r.path)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }, [dirMode, opts.ext])

  useEffect(() => { loadRoots() }, [loadRoots])

  const goUp = () => { if (parent) openDir(parent); else loadRoots() }

  // « Aller » / Entrée : fichier → on valide directement ; dossier → on y navigue.
  const submitManual = () => {
    const p = manual.trim()
    if (!p) return
    if (dirMode) openDir(p)
    else onFinish(p)
  }

  const list = cwd === null ? roots : entries

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => onFinish(null)} />
      <div className="relative rounded-xl w-full max-w-lg shadow-2xl flex flex-col"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)', maxHeight: '80vh' }}>

        {/* En-tête */}
        <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--bg-border)' }}>
          <h2 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            {dirMode ? 'Choose a folder' : 'Choose a file'}{opts.ext ? ` (${opts.ext})` : ''}
          </h2>
          <button onClick={() => onFinish(null)} className="btn-ghost p-1 !gap-0"><X size={16} /></button>
        </div>

        {/* Barre de chemin — saisie manuelle possible */}
        <div className="flex items-center gap-2 px-4 py-2" style={{ borderBottom: '1px solid var(--bg-border)' }}>
          <button onClick={goUp} title="Parent folder"
            className="btn-ghost p-1.5 !gap-0" style={{ flexShrink: 0 }}>
            <CornerLeftUp size={15} />
          </button>
          <input className="input" style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }}
            value={manual}
            placeholder={dirMode ? 'Paste the folder path…' : 'Paste the file path…'}
            autoFocus
            onChange={e => setManual(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && manual.trim()) submitManual() }} />
          <button onClick={submitManual} disabled={!manual.trim()} title="Open this path"
            className="btn-secondary" style={{ flexShrink: 0, fontSize: 12, padding: '6px 10px' }}>
            Go
          </button>
        </div>

        {/* Liste */}
        <div className="overflow-y-auto p-2" style={{ flex: 1, minHeight: 220 }}>
          {loading && (
            <div className="flex justify-center py-10" style={{ color: 'var(--text-muted)' }}>
              <Loader2 size={20} className="animate-spin" />
            </div>
          )}
          {error && !loading && (
            <p className="text-xs px-2 py-3" style={{ color: 'var(--error)' }}>{error}</p>
          )}
          {!loading && !error && list.length === 0 && (
            <p className="text-xs px-2 py-6 text-center" style={{ color: 'var(--text-muted)' }}>
              {dirMode ? 'No subfolders.' : 'No items.'}
            </p>
          )}
          {!loading && list.map(it => (
            <button key={it.path}
              onClick={() => {
                if (it.is_dir) openDir(it.path)
                else if (!dirMode) onFinish(it.path)
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm hover:opacity-80"
              style={{ color: 'var(--text-primary)', background: 'transparent' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              {cwd === null
                ? <HardDrive size={15} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                : it.is_dir
                  ? <Folder size={15} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                  : <FileText size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
              <span className="truncate">{it.name}</span>
            </button>
          ))}
        </div>

        {/* Pied */}
        <div className="flex items-center justify-between gap-2 p-4" style={{ borderTop: '1px solid var(--bg-border)' }}>
          <span className="text-xs truncate" style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>
            {cwd ?? 'Roots'}
          </span>
          <div className="flex gap-2" style={{ flexShrink: 0 }}>
            <button className="btn-secondary" onClick={() => onFinish(null)}>Cancel</button>
            {dirMode && (
              <button className="btn-primary flex items-center gap-1.5"
                disabled={!(manual.trim() || cwd)}
                onClick={() => onFinish(manual.trim() || cwd)}>
                <Check size={14} /> Select this folder
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
