/**
 * TriggerDialog — ajouter ou modifier un déclencheur de projet (onglet Triggers).
 *
 * Un formulaire par type : seules les clés du type choisi sont proposées, puis
 * ce qui est lancé (environnement, workflows, paramètres) et les garde-fous
 * (overlap, timeout, retry). Rien n'est écrit ici : onSave rend la config, que
 * le panneau enregistre avec les autres (PUT /projects/{id}/triggers).
 */
import { useState } from 'react'
import { AlertTriangle, Plus, X, Zap } from 'lucide-react'
import {
  CRON_PRESETS, TRIGGER_TYPES, configFromForm, emptyForm, formFromConfig, formProblems, tokenRef, typeMeta,
  type TriggerConfig, type TriggerForm, type TriggerType,
} from '@/lib/triggers'
import type { Project } from '@/lib/api'

interface Props {
  initial?: TriggerConfig | null
  otherNames: string[]
  workflows: string[]
  sources: { job: string; ids: string[] }[]
  envs: string[]
  projects: Project[]
  currentProjectId: string
  onSave: (c: TriggerConfig) => void
  onClose: () => void
}

export default function TriggerDialog({ initial, otherNames, workflows, sources, envs, projects, currentProjectId, onSave, onClose }: Props) {
  const [f, setF] = useState<TriggerForm>(() => (initial ? formFromConfig(initial) : emptyForm('cron', '')))
  const set = <K extends keyof TriggerForm>(k: K, v: TriggerForm[K]) => setF(x => ({ ...x, [k]: v }))
  const problems = formProblems(f, otherNames)
  const meta = typeMeta(f.type)

  const changeType = (t: TriggerType) => setF(x => ({
    ...emptyForm(t, x.name), description: x.description, enabled: x.enabled, env: x.env, workflows: x.workflows,
    params: x.params, overlap: x.overlap, timeout: x.timeout, retryMax: x.retryMax, retryDelay: x.retryDelay,
  }))
  const changeName = (n: string) => setF(x => ({
    ...x, name: n, token: x.token === tokenRef(x.name) ? tokenRef(n) : x.token,
  }))

  const input: React.CSSProperties = { boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }
  const label: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', margin: '12px 0 4px', display: 'block' }
  const hint: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }
  const mono: React.CSSProperties = { ...input, fontFamily: 'monospace' }
  const field = (lbl: string, el: React.ReactNode, h?: string) => (
    <div>
      <label style={label}>{lbl}{h && <span style={{ ...hint, fontWeight: 400 }}> {h}</span>}</label>
      {el}
    </div>
  )
  const srcIds = sources.find(s => s.job === f.sourceJob)?.ids ?? []

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} data-testid="trigger-dialog"
        style={{ width: 660, maxHeight: '90vh', overflow: 'auto', background: 'var(--bg-card)', borderRadius: 12,
          border: `1px solid ${meta.color}`, padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <Zap size={18} style={{ color: meta.color }} />
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, flex: 1 }}>{initial ? `Trigger ${initial.name}` : 'New trigger'}</h2>
          <button type="button" onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={16} /></button>
        </div>
        <p style={hint}>Starts the whole project (its thread.yaml, or the workflows chosen below) when the event happens.</p>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {field('Name', <input aria-label="Trigger name" style={{ ...mono, width: 220 }} value={f.name}
            onChange={e => changeName(e.target.value)} placeholder="nightly" />)}
          {field('Description', <input aria-label="Description" style={{ ...input, width: 330 }} value={f.description}
            onChange={e => set('description', e.target.value)} placeholder="optional" />)}
        </div>

        <label style={label}>When</label>
        <div data-testid="trigger-types" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
          {TRIGGER_TYPES.map(t => {
            const on = t.id === f.type
            return (
              <button key={t.id} type="button" onClick={() => changeType(t.id)} title={t.hint}
                aria-pressed={on} data-type={t.id}
                style={{ textAlign: 'left', padding: '6px 8px', borderRadius: 8, cursor: 'pointer', fontSize: 11.5,
                  border: `1px solid ${on ? t.color : 'var(--bg-border)'}`,
                  background: on ? `${t.color}22` : 'var(--bg-hover)', color: 'var(--text-primary)' }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 4, background: t.color, marginRight: 6 }} />
                {t.label}
                <div style={{ ...hint, fontFamily: 'monospace', fontSize: 10 }}>{t.id}</div>
              </button>
            )
          })}
        </div>
        <div style={{ ...hint, marginTop: 4 }}>{meta.hint}</div>

        {/* ── Clés du type ── */}
        {f.type === 'cron' && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {field('Cron', <input aria-label="Cron" style={{ ...mono, width: 170 }} value={f.cron}
              onChange={e => set('cron', e.target.value)} />, 'minute hour day month weekday')}
            {field('Preset', (
              <select aria-label="Cron preset" style={{ ...input, width: 200 }} value=""
                onChange={e => e.target.value && set('cron', e.target.value)}>
                <option value="">Choose…</option>
                {CRON_PRESETS.map(p => <option key={p.cron} value={p.cron}>{p.label}</option>)}
              </select>
            ))}
            {field('Time zone', <input aria-label="Time zone" style={{ ...mono, width: 150 }} value={f.timezone}
              onChange={e => set('timezone', e.target.value)} placeholder="Europe/Paris" />, '(default: the machine)')}
          </div>
        )}
        {f.type === 'interval' && field('Every', <input aria-label="Every" style={{ ...mono, width: 120 }} value={f.every}
          onChange={e => set('every', e.target.value)} placeholder="15m" />, '30s, 5m, 1h')}
        {(f.type === 'file' || f.type === 'marker') && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {field('Path', <input aria-label="Path" style={{ ...mono, width: 260 }} value={f.path}
              onChange={e => set('path', e.target.value)} placeholder={f.type === 'marker' ? 'inbox/READY' : 'inbox/*.csv'} />,
              'in the project; ** for subfolders')}
            {f.type === 'file' && field('Events', (
              <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
                {(['added', 'modified'] as const).map(ev => (
                  <label key={ev} style={{ fontSize: 12, display: 'inline-flex', gap: 4 }}>
                    <input type="checkbox" checked={f.events.includes(ev)}
                      onChange={e => set('events', e.target.checked ? [...f.events, ev] : f.events.filter(x => x !== ev))} /> {ev}
                  </label>
                ))}
              </div>
            ))}
            {f.type === 'file' && field('Debounce', <input aria-label="Debounce" style={{ ...mono, width: 80 }} value={f.debounce}
              onChange={e => set('debounce', e.target.value)} placeholder="2s" />)}
            {f.type === 'marker' && field('After the start', (
              <label style={{ fontSize: 12, display: 'inline-flex', gap: 4, paddingTop: 4 }}>
                <input type="checkbox" checked={f.consume} onChange={e => set('consume', e.target.checked)} /> remove the marker
              </label>
            ))}
            {field('Check every', <input aria-label="Check every" style={{ ...mono, width: 80 }} value={f.every}
              onChange={e => set('every', e.target.value)} placeholder="5s" />)}
          </div>
        )}
        {f.type === 'source_change' && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {field('Job', (
              <select aria-label="Source job" style={{ ...input, width: 170 }} value={f.sourceJob}
                onChange={e => setF(x => ({ ...x, sourceJob: e.target.value, sourceId: sources.find(s => s.job === e.target.value)?.ids[0] ?? '' }))}>
                <option value="">Choose…</option>
                {sources.map(s => <option key={s.job} value={s.job}>{s.job}</option>)}
              </select>
            ))}
            {field('Source', (
              <select aria-label="Source id" style={{ ...input, width: 140 }} value={f.sourceId} onChange={e => set('sourceId', e.target.value)}>
                {srcIds.length === 0 && <option value="">—</option>}
                {srcIds.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            ))}
            {field('Check', (
              <select aria-label="Check" style={{ ...input, width: 140 }} value={f.sourceCheck}
                onChange={e => set('sourceCheck', e.target.value as TriggerForm['sourceCheck'])}>
                <option value="count">count (rows)</option><option value="max">max of a column</option><option value="checksum">checksum</option>
              </select>
            ))}
            {f.sourceCheck === 'max' && field('Column', <input aria-label="Column" style={{ ...mono, width: 130 }} value={f.sourceColumn}
              onChange={e => set('sourceColumn', e.target.value)} placeholder="updated_at" />)}
            {field('Check every', <input aria-label="Check every" style={{ ...mono, width: 80 }} value={f.every}
              onChange={e => set('every', e.target.value)} placeholder="1m" />)}
          </div>
        )}
        {f.type === 'webhook' && (<>
          {field('Token', <input aria-label="Token" style={{ ...mono, width: 360 }} value={f.token}
            onChange={e => set('token', e.target.value)} />, 'a secret reference — create the value after saving')}
          <div style={{ ...hint, marginTop: 4 }}>The caller sends <code>POST …/triggers/{f.name || 'name'}/webhook</code> with the header <code>X-Hydra-Token</code>.</div>
        </>)}
        {f.type === 'after_project' && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {field('Project', <input aria-label="After project" style={{ ...mono, width: 220 }} value={f.project}
              onChange={e => set('project', e.target.value)} placeholder={f.ref === 'path' ? '../crm' : 'crm'} />)}
            {field('', (
              <select aria-label="Open project" style={{ ...input, width: 190 }} value=""
                onChange={e => { const p = projects.find(x => x.id === e.target.value); if (p) setF(x => ({ ...x, project: p.name, ref: 'name' })) }}>
                <option value="">Choose an open project…</option>
                {projects.filter(p => p.id !== currentProjectId).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ))}
            {field('Read as', (
              <select aria-label="Reference" style={{ ...input, width: 150 }} value={f.ref} onChange={e => set('ref', e.target.value as 'path' | 'name')}>
                <option value="path">path (git)</option><option value="name">Studio name</option>
              </select>
            ))}
            {field('On', (
              <select aria-label="On" style={{ ...input, width: 110 }} value={f.on} onChange={e => set('on', e.target.value as TriggerForm['on'])}>
                <option value="success">success</option><option value="failure">failure</option><option value="any">any end</option>
              </select>
            ))}
          </div>
        )}

        {/* ── Ce qui est lancé ── */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {field('Environment', (
            <select aria-label="Environment" style={{ ...input, width: 190 }} value={f.env} onChange={e => set('env', e.target.value)}>
              <option value="">from watch / serve</option>
              {envs.map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          ))}
          {field('If already running', (
            <select aria-label="Overlap" style={{ ...input, width: 120 }} value={f.overlap} onChange={e => set('overlap', e.target.value as TriggerForm['overlap'])}>
              <option value="skip">skip</option><option value="wait">wait</option><option value="fail">fail</option>
            </select>
          ))}
          {field('Timeout', <input aria-label="Timeout" style={{ ...mono, width: 80 }} value={f.timeout}
            onChange={e => set('timeout', e.target.value)} placeholder="1h" />)}
          {field('Retries', <input aria-label="Retries" style={{ ...mono, width: 60 }} value={f.retryMax}
            onChange={e => set('retryMax', e.target.value)} placeholder="0" />)}
          {f.retryMax.trim() && field('after', <input aria-label="Retry delay" style={{ ...mono, width: 70 }} value={f.retryDelay}
            onChange={e => set('retryDelay', e.target.value)} placeholder="1m" />)}
        </div>

        <label style={label}>Workflows to run <span style={hint}>(none checked: the project's thread.yaml)</span></label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          {workflows.map(w => (
            <label key={w} style={{ fontSize: 12, display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              <input type="checkbox" checked={f.workflows.includes(w)}
                onChange={e => set('workflows', e.target.checked ? [...f.workflows, w] : f.workflows.filter(x => x !== w))} /> {w}
            </label>
          ))}
        </div>

        <label style={label}>Parameters <span style={hint}>(like -P; the event also gives trigger.file, trigger.value, trigger.project…)</span></label>
        {f.params.map((p, i) => (
          <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
            <input style={{ ...mono, width: 170 }} value={p.key} placeholder="name" aria-label={`Parameter ${i + 1} name`}
              onChange={e => set('params', f.params.map((x, j) => j === i ? { ...x, key: e.target.value } : x))} />
            <input style={{ ...input, flex: 1 }} value={p.value} placeholder="value" aria-label={`Parameter ${i + 1} value`}
              onChange={e => set('params', f.params.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
            <button type="button" onClick={() => set('params', f.params.filter((_, j) => j !== i))}
              style={{ border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', borderRadius: 6, color: 'var(--text-muted)', cursor: 'pointer' }}><X size={12} /></button>
          </div>
        ))}
        <button type="button" className="btn-secondary text-xs" onClick={() => set('params', [...f.params, { key: '', value: '' }])}>
          <Plus size={12} /> Add a parameter
        </button>

        <label style={{ ...label, display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={f.enabled} onChange={e => set('enabled', e.target.checked)} /> Enabled
          <span style={{ ...hint, fontWeight: 400 }}>(off: kept, not watched; Run now still works)</span>
        </label>

        {problems.length > 0 && (
          <div data-testid="trigger-problems" style={{ marginTop: 10, fontSize: 12 }}>
            {problems.map((p, i) => <div key={i} style={{ color: 'var(--warning)' }}><AlertTriangle size={12} /> {p}</div>)}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button type="button" className="btn-secondary text-xs" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary text-xs" disabled={problems.length > 0}
            data-testid="trigger-dialog-ok" onClick={() => onSave(configFromForm(f))}
            style={{ opacity: problems.length ? 0.5 : 1 }}>
            {initial ? 'Apply' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  )
}
