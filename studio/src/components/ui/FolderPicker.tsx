/**
 * FolderPicker — explorateur de dossiers/fichiers 100 % web.
 *
 * Remplace le dialogue natif côté serveur (api.system.browse) qui ne peut pas
 * s'afficher quand le backend tourne sans display (WSL, Docker, serveur distant).
 *
 * Usage impératif, compatible avec l'ancien code :
 *   const res = await pickPath('directory')       // { path: string | null }
 *   const res = await pickPath('file', '.csv')
 *   const res = await pickPath('directory', '', { confirmLabel: 'Select a project', projectOnly: true })
 *
 * Mode dossier : un clic SELECTIONNE le dossier, un double clic l'OUVRE
 * (navigation vers ses sous-dossiers). Le bouton valide le dossier selectionne,
 * ou le dossier courant si rien n'est selectionne. Un projet Hydra est reconnu par son
 * marqueur `.hydra/project.json` (champ `is_project` renvoye par /fs/list) et porte un badge ;
 * avec `projectOnly`, le bouton n'est actif que sur un projet.
 *
 * Requiert que <FolderPickerHost /> soit monté une fois à la racine de l'app.
 */
import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { Folder, FileText, CornerLeftUp, HardDrive, X, Check, Loader2 } from 'lucide-react'

type PickType = 'file' | 'directory' | 'save_file'
interface PickResult { path: string | null }
interface PickOpts { type: PickType; ext: string; confirmLabel?: string; projectOnly?: boolean }
export interface PickPathOptions { confirmLabel?: string; projectOnly?: boolean }

// ── Pont impératif ──────────────────────────────────────────────────────────
let _openImpl: ((opts: PickOpts) => Promise<PickResult>) | null = null

export function pickPath(type: PickType, ext = '', options: PickPathOptions = {}): Promise<PickResult> {
  if (_openImpl) return _openImpl({ type, ext, confirmLabel: options.confirmLabel, projectOnly: options.projectOnly })
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
interface Entry { name: string; path: string; is_dir: boolean; is_project?: boolean }

function PickerModal({ opts, onFinish }: { opts: PickOpts; onFinish: (p: string | null) => void }) {
  const dirMode = opts.type === 'directory'
  const [cwd, setCwd] = useState<string | null>(null)          // null = vue racines
  const [parent, setParent] = useState<string | null>(null)
  const [cwdIsProject, setCwdIsProject] = useState(false)
  const [entries, setEntries] = useState<Entry[]>([])
  const [roots, setRoots] = useState<Entry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [manual, setManual] = useState('')
  // Mode dossier : dossier surligne par un clic simple (non encore ouvert).
  const [selected, setSelected] = useState<string | null>(null)

  const loadRoots = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await api.system.fsRoots()
      setRoots(r.roots.map(x => ({ ...x, is_dir: true })))
      setCwd(null); setParent(null); setEntries([]); setSelected(null); setCwdIsProject(false)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }, [])

  const openDir = useCallback(async (path: string) => {
    setLoading(true); setError(null)
    try {
      const r = await api.system.fsList(path, dirMode, opts.ext)
      setCwd(r.path); setParent(r.parent); setEntries(r.entries); setManual(r.path); setSelected(null)
      setCwdIsProject(!!r.is_project)
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

  // Le dossier que validerait le bouton, et s'il est un projet Hydra.
  //  - un dossier surligne : son propre indicateur ;
  //  - sinon le dossier courant (ou le chemin saisi tel quel) : indicateur du dossier liste ;
  //  - chemin saisi different du dossier liste : inconnu -> on laisse le serveur valider.
  const selectedEntry = selected ? entries.find(en => en.path === selected) : undefined
  const targetPath = selected ?? (manual.trim() || cwd)
  const targetIsProject: boolean | undefined =
    selected ? !!selectedEntry?.is_project
    : (cwd !== null && manual.trim() === cwd) ? cwdIsProject
    : undefined
  const blockedByProjectOnly = !!opts.projectOnly && targetIsProject !== true

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
            onChange={e => { setManual(e.target.value); setSelected(null) }}
            onKeyDown={e => { if (e.key === 'Enter' && manual.trim()) submitManual() }} />
          <button onClick={submitManual} disabled={!manual.trim()} title="Open this path"
            className="btn-secondary" style={{ flexShrink: 0, fontSize: 12, padding: '6px 10px' }}>
            Go
          </button>
        </div>

        {dirMode && (
          <p className="text-xs px-4 pt-2" style={{ color: 'var(--text-muted)' }}>
            Click a folder to select it · double-click to open it
          </p>
        )}

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
          {!loading && list.map(it => {
            const isSel = dirMode && selected === it.path
            return (
            <button key={it.path}
              // Mode dossier : clic = selection, double clic = ouverture.
              // Mode fichier : clic sur un dossier = ouverture, clic sur un fichier = choix.
              onClick={() => {
                if (dirMode) { if (it.is_dir) setSelected(it.path) }
                else if (it.is_dir) openDir(it.path)
                else onFinish(it.path)
              }}
              onDoubleClick={() => { if (dirMode && it.is_dir) openDir(it.path) }}
              aria-selected={isSel}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm hover:opacity-80"
              style={{
                color: 'var(--text-primary)',
                background: isSel ? 'var(--primary-subtle)' : 'transparent',
                outline: isSel ? '1px solid var(--primary)' : 'none',
              }}
              onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={e => { e.currentTarget.style.background = isSel ? 'var(--primary-subtle)' : 'transparent' }}
            >
              {cwd === null
                ? <HardDrive size={15} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                : it.is_dir
                  ? <Folder size={15} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                  : <FileText size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
              <span className="truncate">{it.name}</span>
              {it.is_dir && it.is_project && (
                <span title="Hydra project (.hydra/project.json)"
                  style={{
                    marginLeft: 'auto', flexShrink: 0, fontSize: 10, fontWeight: 600,
                    padding: '1px 7px', borderRadius: 999,
                    color: 'var(--primary)', background: 'var(--primary-subtle)',
                    border: '1px solid var(--primary)',
                  }}>
                  Hydra project
                </span>
              )}
            </button>
            )
          })}
        </div>

        {/* Pied */}
        <div className="flex items-center justify-between gap-2 p-4" style={{ borderTop: '1px solid var(--bg-border)' }}>
          <span className="text-xs truncate" style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}
            title={dirMode ? 'Click to select · double-click to open' : undefined}>
            {dirMode && selected ? selected : (cwd ?? 'Roots')}
            {dirMode && cwd !== null && !selected && cwdIsProject ? '  ·  Hydra project' : ''}
          </span>
          <div className="flex gap-2" style={{ flexShrink: 0 }}>
            <button className="btn-secondary" onClick={() => onFinish(null)}>Cancel</button>
            {dirMode && (
              <button className="btn-primary flex items-center gap-1.5"
                disabled={!(selected || manual.trim() || cwd) || blockedByProjectOnly}
                title={blockedByProjectOnly ? 'This folder is not a Hydra project (no .hydra/project.json)' : undefined}
                onClick={() => onFinish(targetPath)}>
                <Check size={14} /> {opts.confirmLabel ?? 'Select this folder'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
