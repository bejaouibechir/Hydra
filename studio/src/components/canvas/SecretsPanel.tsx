/**
 * SecretsPanel — onglet « Secrets » du volet bas.
 *
 * Gère le fichier de secrets du projet : .hydra/secrets (une ligne name=value,
 * ignoré par git), ou le fichier désigné par HYDRA_SECRETS_FILE. Le moteur le
 * lit pour ${SECRET:name}, après les variables d'environnement (qui gagnent).
 *
 * Les valeurs ne reviennent jamais de l'API : la liste n'affiche que les noms.
 * On peut ajouter, remplacer (en ressaisissant la valeur) ou supprimer.
 */
import { useState } from 'react'
import { Plus, Trash2, Loader2, KeyRound, Copy } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type SecretsInfo } from '@/lib/api'
import { useActiveEnv } from '@/lib/activeEnv'

interface Props { projectId: string; accent?: string }

const NAME_RE = /^[A-Za-z0-9_.-]+$/

export default function SecretsPanel({ projectId, accent = 'var(--primary)' }: Props) {
  const qc = useQueryClient()
  // Portée : secrets communs (.hydra/secrets) ou d'un environnement (.hydra/secrets.<env>)
  const [activeEnv] = useActiveEnv(projectId)
  const [scope, setScope] = useState<string>(activeEnv)
  const names = useQuery({ queryKey: ['env-names', projectId], queryFn: () => api.globalEnv.names(projectId), enabled: Boolean(projectId) })
  const envs = (names.data ?? []).map(n => n.name)
  const key = ['secrets', projectId, scope]
  const { data, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: () => api.secrets.list(projectId, scope || null),
    enabled: Boolean(projectId),
  })
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  const onDone = (d: SecretsInfo) => {
    qc.setQueryData(key, d)
    qc.invalidateQueries({ queryKey: ['secrets', projectId] })
    qc.invalidateQueries({ queryKey: ['env-names'] })
  }
  const setMut = useMutation({
    mutationFn: () => api.secrets.set(projectId, name.trim(), value, scope || null),
    onSuccess: d => { onDone(d); setName(''); setValue('') },
  })
  const delMut = useMutation({
    // Supprime dans le fichier d'où vient le secret (commun ou environnement)
    mutationFn: (s: { name: string; scope?: string }) =>
      api.secrets.remove(projectId, s.name, s.scope && s.scope !== 'common' ? s.scope : null),
    onSuccess: async () => onDone(await api.secrets.list(projectId, scope || null)),
  })

  const copyRef = (n: string) => {
    const ref = '${SECRET:' + n + '}'
    navigator.clipboard?.writeText(ref).catch(() => {})
    setCopied(n)
    setTimeout(() => setCopied(c => (c === n ? null : c)), 1500)
  }

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
  }
  const muted: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }

  if (!projectId) return <div style={{ padding: 12, ...muted }}>Open a project to manage its secrets.</div>
  if (isLoading) return <div style={{ padding: 12, ...muted, display: 'flex', gap: 6, alignItems: 'center' }}><Loader2 size={13} /> Loading…</div>
  if (error) return <div style={{ padding: 12, fontSize: 12, color: 'var(--error)' }}>{(error as Error).message}</div>

  const exists = data?.secrets.some(s => s.name === name.trim() && (s.scope ?? 'common') === (scope || 'common'))
  const nameOk = NAME_RE.test(name.trim())

  return (
    <div data-testid="secrets-panel" style={{ height: '100%', overflow: 'auto', padding: '4px 4px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Secrets for</span>
        <select aria-label="Secrets scope" value={scope} onChange={e => setScope(e.target.value)}
          style={{ ...input, cursor: 'pointer', minWidth: 160 }}>
          <option value="">Common (all environments)</option>
          {envs.map(en => <option key={en} value={en}>{en}{en === activeEnv ? ' (active)' : ''}</option>)}
        </select>
        <span style={{ ...muted, fontFamily: 'monospace' }}>{scope ? data?.env_file : data?.file}</span>
      </div>
      <div style={{ ...muted, marginBottom: 8, lineHeight: 1.5 }}>
        <KeyRound size={12} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 4 }} />
        File <code>{data?.file}</code>{data?.external ? ' (set by HYDRA_SECRETS_FILE)' : ' — ignored by git'}.
        {' '}Use a secret as <code>{'${SECRET:name}'}</code> in any field. An environment variable with the
        same name in upper case (<code>db.password</code> → <code>DB_PASSWORD</code>) wins over the file.
        Values are never displayed: type a new value to replace one.
        {' '}A secret of an environment wins over the common one when a run uses that environment.
      </div>

      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <thead>
          <tr>
            {['Name', 'Value', 'From', 'Reference', ''].map(h => (
              <th key={h} style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', padding: '0 6px 4px' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(data?.secrets ?? []).map(s => (
            <tr key={s.name}>
              <td style={{ padding: '3px 6px', fontFamily: 'monospace' }}>{s.name}</td>
              <td style={{ padding: '3px 6px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                ••••••
                {s.overridden_by && (
                  <span title="This environment variable is set: it is used instead of the file"
                    style={{ marginLeft: 8, fontSize: 10, color: 'var(--warning)' }}>
                    overridden by ${s.overridden_by}
                  </span>
                )}
              </td>
              <td style={{ padding: '3px 6px', ...muted, color: (s.scope ?? 'common') === 'common' ? 'var(--text-muted)' : accent }}>
                {(s.scope ?? 'common') === 'common' ? 'common' : s.scope}
              </td>
              <td style={{ padding: '3px 6px' }}>
                <button type="button" onClick={() => copyRef(s.name)} title="Copy the reference"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'transparent', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '2px 8px', color: accent, cursor: 'pointer', fontSize: 11, fontFamily: 'monospace' }}>
                  <Copy size={11} /> {copied === s.name ? 'copied' : '${SECRET:' + s.name + '}'}
                </button>
              </td>
              <td style={{ padding: 3, width: 28 }}>
                <button type="button" title="Delete" disabled={delMut.isPending}
                  onClick={() => { if (window.confirm(`Delete the secret '${s.name}' (${s.scope ?? 'common'})?`)) delMut.mutate(s) }}
                  style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                  <Trash2 size={12} />
                </button>
              </td>
            </tr>
          ))}
          {(data?.secrets.length ?? 0) === 0 && (
            <tr><td colSpan={5} style={{ padding: 10, ...muted }}>No secret yet.</td></tr>
          )}
        </tbody>
      </table>

      <form onSubmit={e => { e.preventDefault(); if (nameOk && value) setMut.mutate() }}
        style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <input style={{ ...input, width: 180 }} value={name} onChange={e => setName(e.target.value)}
          placeholder="db.password" aria-label="Secret name" />
        <input style={{ ...input, width: 220 }} type="password" autoComplete="new-password"
          value={value} onChange={e => setValue(e.target.value)} placeholder="value" aria-label="Secret value" />
        <button type="submit" disabled={!nameOk || !value || setMut.isPending}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: 'none', background: accent, color: '#fff', cursor: 'pointer', opacity: (!nameOk || !value) ? 0.5 : 1 }}>
          {setMut.isPending ? <Loader2 size={13} /> : <Plus size={13} />} {exists ? 'Replace' : 'Add'}{scope ? ` to ${scope}` : ''}
        </button>
        {name && !nameOk && <span style={{ fontSize: 11, color: 'var(--error)' }}>letters, digits, '.', '_' or '-'</span>}
        {setMut.isError && <span style={{ fontSize: 11, color: 'var(--error)' }}>{(setMut.error as Error).message}</span>}
        {delMut.isError && <span style={{ fontSize: 11, color: 'var(--error)' }}>{(delMut.error as Error).message}</span>}
      </form>
    </div>
  )
}
