/**
 * NodeConfigDialog — Modale de configuration d'un nœud Hydra.
 * Déclencheurs : double-clic sur le nœud, ou context-menu "Configure"
 */
import { useState, useCallback, useEffect } from 'react'
import type { Node } from '@xyflow/react'
import { X, FolderOpen, Eye, EyeOff } from 'lucide-react'
import { getNode } from '@/lib/nodeRegistry'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { api } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import JobCreatorWizard from '@/components/canvas/JobCreatorWizard'
import ExpressionBuilder from '@/components/canvas/ExpressionBuilder'
import { rewriteFriendlyConcat } from '@/lib/exprBuilder'

// ── Définition d'un champ de config ──────────────────────────────────────────

interface FieldDef {
  key: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'select' | 'password'
  placeholder?: string
  required?: boolean
  options?: string[]
  browseType?: 'file' | 'directory' | 'save_file'  // active le bouton Parcourir
  browseExt?:  string                                // filtre extension ex: '.csv'
}

// ── Champs par type de nœud ───────────────────────────────────────────────────

const CONFIG_FIELDS: Record<string, FieldDef[]> = {
  // Sources
  source_csv:     [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './data/file.csv',     required: true, browseType: 'file',      browseExt: '.csv' }],
  source_json:    [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './data/file.json',    required: true, browseType: 'file',      browseExt: '.json' }],
  source_parquet: [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './data/file.parquet', required: true, browseType: 'file',      browseExt: '.parquet' }],
  source_mysql:    [
    { key: 'host',     label: 'Hôte',        type: 'text',   placeholder: 'localhost', required: true },
    { key: 'port',     label: 'Port',        type: 'number', placeholder: '3306' },
    { key: 'database', label: 'Base',        type: 'text',   required: true },
    { key: 'user',     label: 'Utilisateur', type: 'text',   required: true },
    { key: 'password', label: 'Mot de passe', type: 'password' },
    { key: 'table',    label: 'Table',        type: 'text' },
    { key: 'query',    label: 'Requête SQL',  type: 'textarea' },
  ],
  source_postgres: [
    { key: 'host',     label: 'Hôte',        type: 'text',   placeholder: 'localhost', required: true },
    { key: 'port',     label: 'Port',        type: 'number', placeholder: '5432' },
    { key: 'database', label: 'Base',        type: 'text',   required: true },
    { key: 'user',     label: 'Utilisateur', type: 'text',   required: true },
    { key: 'password', label: 'Mot de passe', type: 'password' },
    { key: 'table',    label: 'Table',        type: 'text' },
    { key: 'query',    label: 'Requête SQL',  type: 'textarea' },
  ],
  source_mongodb:  [
    { key: 'uri',        label: 'URI MongoDB', type: 'text', placeholder: 'mongodb://localhost:27017', required: true },
    { key: 'database',   label: 'Base',        type: 'text', required: true },
    { key: 'collection', label: 'Collection',  type: 'text', required: true },
  ],
  source_api: [
    { key: 'url',    label: 'URL',     type: 'text',   required: true },
    { key: 'method', label: 'Méthode', type: 'select', options: ['GET', 'POST', 'PUT', 'DELETE'] },
  ],
  // Destinations
  dest_csv:     [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './output/file.csv',     required: true, browseType: 'save_file', browseExt: '.csv' }],
  dest_json:    [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './output/file.json',    required: true, browseType: 'save_file', browseExt: '.json' }],
  dest_parquet: [{ key: 'path', label: 'Chemin fichier', type: 'text', placeholder: './output/file.parquet', required: true, browseType: 'save_file', browseExt: '.parquet' }],
  dest_mysql:    [
    { key: 'host',     label: 'Hôte',        type: 'text',   placeholder: 'localhost', required: true },
    { key: 'port',     label: 'Port',        type: 'number', placeholder: '3306' },
    { key: 'database', label: 'Base',        type: 'text',   required: true },
    { key: 'user',     label: 'Utilisateur', type: 'text',   required: true },
    { key: 'password', label: 'Mot de passe', type: 'password' },
    { key: 'table',    label: 'Table',       type: 'text',   required: true },
    { key: 'mode',     label: 'Mode',        type: 'select', options: ['append', 'replace', 'upsert'] },
  ],
  dest_postgres: [
    { key: 'host',     label: 'Hôte',        type: 'text',   placeholder: 'localhost', required: true },
    { key: 'port',     label: 'Port',        type: 'number', placeholder: '5432' },
    { key: 'database', label: 'Base',        type: 'text',   required: true },
    { key: 'user',     label: 'Utilisateur', type: 'text',   required: true },
    { key: 'password', label: 'Mot de passe', type: 'password' },
    { key: 'table',    label: 'Table',       type: 'text',   required: true },
    { key: 'mode',     label: 'Mode',        type: 'select', options: ['append', 'replace', 'upsert'] },
  ],
  dest_mongodb:  [
    { key: 'uri',        label: 'URI MongoDB', type: 'text', required: true },
    { key: 'database',   label: 'Base',        type: 'text', required: true },
    { key: 'collection', label: 'Collection',  type: 'text', required: true },
  ],
  // Transformations
  transform_filter:    [{ key: 'expr',    label: 'Expression',                  type: 'text',     placeholder: "status == 'active'",              required: true }],
  transform_select:    [{ key: 'columns', label: 'Colonnes (séparées par ,)',    type: 'text',     placeholder: 'id, name, email',                 required: true }],
  transform_rename:    [{ key: 'mapping', label: 'Mapping (JSON)',               type: 'textarea', placeholder: '{"old_col": "new_col"}',           required: true }],
  transform_cast:      [{ key: 'mapping', label: 'Types (JSON)',                 type: 'textarea', placeholder: '{"price": "float", "qty": "int"}', required: true }],
  transform_sort:      [
    { key: 'by',        label: 'Colonnes de tri (séparées par ,)', type: 'text', placeholder: 'score, name', required: true },
    { key: 'ascending', label: 'Ordre', type: 'select', options: ['ASC', 'DESC'] },
  ],
  transform_aggregate: [
    { key: 'by',  label: 'Group by (séparées par ,)', type: 'text',     placeholder: 'category, region', required: true },
    { key: 'agg', label: 'Agrégations (JSON)',         type: 'textarea', placeholder: '{"total": {"func": "sum", "col": "amount"}}', required: true },
  ],
  transform_dedupe: [{ key: 'columns', label: 'Colonnes (vide = toutes)', type: 'text', placeholder: 'id, email' }],
  transform_derive: [
    { key: 'column', label: 'Nouvelle colonne', type: 'text', placeholder: 'revenue',          required: true },
    { key: 'expr',   label: 'Expression',       type: 'text', placeholder: 'unit_price * qty', required: true },
  ],
  transform_join: [
    { key: 'key',       label: 'Clé (colonne commune)',       type: 'text',   placeholder: 'email' },
    { key: 'left_key',  label: 'Clé gauche (si différente)',  type: 'text',   placeholder: 'manager_id' },
    { key: 'right_key', label: 'Clé droite (si différente)',  type: 'text',   placeholder: 'id' },
    { key: 'how',       label: 'Type de jointure',            type: 'select', options: ['inner', 'left', 'right', 'outer'] },
  ],
  // Actions génériques
  action_webhook: [
    { key: 'url',     label: 'URL',           type: 'text',     placeholder: 'https://example.com/hook', required: true },
    { key: 'method',  label: 'Méthode',       type: 'select',   options: ['POST', 'GET', 'PUT', 'PATCH', 'DELETE'] },
    { key: 'body',    label: 'Body (JSON)',    type: 'textarea', placeholder: '{"key": "value"}' },
    { key: 'headers', label: 'Headers (JSON)', type: 'textarea', placeholder: '{"Authorization": "Bearer ..."}' },
  ],
  action_email: [
    { key: 'to',        label: 'Destinataire',      type: 'text',     required: true, placeholder: 'user@example.com' },
    { key: 'subject',   label: 'Sujet',             type: 'text',     required: true },
    { key: 'body',      label: 'Corps',             type: 'textarea' },
    { key: 'from_addr', label: 'Expéditeur (From)', type: 'text',     placeholder: 'hydra@localhost' },
    { key: 'smtp_host', label: 'Serveur SMTP',      type: 'text',     placeholder: 'localhost' },
    { key: 'smtp_port', label: 'Port SMTP',         type: 'number',   placeholder: '1025' },
    { key: 'username',  label: 'Utilisateur SMTP',  type: 'text' },
    { key: 'password',  label: 'Mot de passe SMTP', type: 'password' },
    { key: 'use_tls',   label: 'TLS (STARTTLS)',    type: 'select',   options: ['false', 'true'] },
  ],
  // Actions shell
  action_bash: [
    { key: 'command',     label: 'Commande Bash',         type: 'textarea', placeholder: 'echo "hello" && ls -la', required: true },
    { key: 'working_dir', label: 'Répertoire de travail', type: 'text',     placeholder: '/home/user/project', browseType: 'directory' },
    { key: 'timeout',     label: 'Timeout (secondes)',    type: 'number',   placeholder: '60' },
  ],
  action_powershell: [
    { key: 'command',     label: 'Commande PowerShell',   type: 'textarea', placeholder: 'Get-Process | Select-Object Name, CPU', required: true },
    { key: 'working_dir', label: 'Répertoire de travail', type: 'text',     placeholder: 'C:\\Users\\...\\project', browseType: 'directory' },
    { key: 'timeout',     label: 'Timeout (secondes)',    type: 'number',   placeholder: '60' },
  ],
  action_ssh: [
    { key: 'host',     label: 'Hôte',               type: 'text',     required: true },
    { key: 'port',     label: 'Port',               type: 'number',   placeholder: '22' },
    { key: 'username', label: 'Utilisateur',         type: 'text',     required: true },
    { key: 'password', label: 'Mot de passe',        type: 'password' },
    { key: 'key_path', label: 'Clé privée (chemin)', type: 'text',     placeholder: '~/.ssh/id_rsa', browseType: 'file' },
    { key: 'command',  label: 'Commande distante',   type: 'textarea', required: true },
    { key: 'timeout',  label: 'Timeout (secondes)',  type: 'number' },
  ],
  action_python: [
    { key: 'script',      label: 'Script inline',              type: 'textarea', placeholder: 'import sys\nprint(sys.version)' },
    { key: 'file_path',   label: 'Ou chemin vers fichier .py', type: 'text',     placeholder: '/home/user/script.py',  browseType: 'file',      browseExt: '.py' },
    { key: 'working_dir', label: 'Répertoire de travail',      type: 'text',     placeholder: '/home/user/project',    browseType: 'directory' },
    { key: 'timeout',     label: 'Timeout (secondes)',          type: 'number',   placeholder: '60' },
  ],
}

// Nœuds action "shell" — pas de dropdown "Action type"
const SHELL_ACTION_TYPES = new Set(['action_powershell', 'action_bash', 'action_ssh'])

// Sources DB — choix mutuellement exclusif Table / Requête SQL
const DB_SOURCE_TYPES = new Set(['source_mysql', 'source_postgres'])

// ── Couleur par catégorie ─────────────────────────────────────────────────────

const CATEGORY_ACCENT: Record<string, string> = {
  source:         'var(--success)',
  transformation: 'var(--primary)',
  destination:    'var(--warning)',
  action:         'var(--info)',
}

// ── Icône Lucide par nom ──────────────────────────────────────────────────────

import {
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge,
  Webhook, MessageSquare, Mail, Terminal, Network, Code,
  GitBranch, LayoutGrid, Clock, Scissors, Link2,
  Briefcase,
} from 'lucide-react'
import { MySQLIcon, PostgreSQLIcon } from '@/components/icons/DatabaseIcons'

const LUCIDE: Record<string, React.ElementType> = {
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge,
  Webhook, MessageSquare, Mail, Terminal, Network, Code,
  GitBranch, LayoutGrid, Clock, Scissors, Link2,
  MySQL: MySQLIcon, PostgreSQL: PostgreSQLIcon,
  Briefcase,
}

function resolveIcon(name?: string): React.ElementType {
  return (name && LUCIDE[name]) ? LUCIDE[name] : Briefcase
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  node:    Node<FlowNodeData>
  onClose: () => void
  onSave:  (id: string, patch: Partial<FlowNodeData>) => void
  joinSources?: { id: string; label: string }[]   // sources du canvas (pour le noeud join)
}

// ── Composant ─────────────────────────────────────────────────────────────────

export default function NodeConfigDialog({ node, onClose, onSave, joinSources = [] }: Props) {
  const d   = node.data
  const def = getNode(d.nodeType)

  const accent = CATEGORY_ACCENT[def?.category ?? 'source'] ?? 'var(--primary)'
  const Icon   = resolveIcon(def?.icon)

  const [stepName,  setStepName]  = useState(d.stepName ?? '')
  const [jobPath,   setJobPath]   = useState(d.jobPath  ?? '')
  const [onFailure, setOnFailure] = useState<'fail' | 'skip' | 'continue'>(d.onFailure ?? 'fail')
  const [params,    setParams]    = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries((d.params as Record<string, unknown>) ?? {}).map(([k, v]) => [k, String(v ?? '')])
    )
  )
  // Mode Python : 'inline' si script renseigné ou pas de file_path, 'file' sinon
  const initPythonMode = (): 'inline' | 'file' => {
    const p = (d.params as Record<string, string>) ?? {}
    return p.file_path?.trim() ? 'file' : 'inline'
  }
  const [pythonMode, setPythonMode] = useState<'inline' | 'file'>(initPythonMode)
  const [browsing,   setBrowsing]   = useState(false)
  // Mode job : 'existing' (jobPath manuel) ou 'new' (wizard)
  const [jobMode,    setJobMode]    = useState<'existing' | 'new'>('existing')
  // Mode source DB : 'table' ou 'query' (mutuellement exclusifs)
  const isDbSource = DB_SOURCE_TYPES.has(d.nodeType)
  const initSourceMode = (): 'table' | 'query' => {
    const p = (d.params as Record<string, string>) ?? {}
    return p.query?.trim() ? 'query' : 'table'
  }
  const [sourceMode, setSourceMode] = useState<'table' | 'query'>(initSourceMode)
  // Révélation des champs mot de passe (par clé)
  const [revealed,   setRevealed]   = useState<Record<string, boolean>>({})
  const [showExprBuilder, setShowExprBuilder] = useState(false)
  // Join : mode 'common' (cle commune) ou 'distinct' (self-join / FK != PK)
  const initJoinMode = (): 'common' | 'distinct' => {
    const p = (d.params as Record<string, string>) ?? {}
    return (p.left_key?.trim() || p.right_key?.trim()) ? 'distinct' : 'common'
  }
  const [joinMode, setJoinMode] = useState<'common' | 'distinct'>(initJoinMode)
  // sysInfo : utilisé pour vérifier la disponibilité du backend browse (optionnel)
  useQuery({ queryKey: ['system-info'], queryFn: api.system.info, staleTime: Infinity })

  const setParam = useCallback((key: string, value: string) => {
    setParams(p => ({ ...p, [key]: value }))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSave()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, stepName, jobPath, onFailure, params])

  const handleSave = () => {
    let finalParams = params
    if (d.nodeType === 'transform_derive' && params.expr) {
      finalParams = { ...params, expr: rewriteFriendlyConcat(params.expr) }
    }
    onSave(node.id, {
      stepName:  stepName.trim() || d.stepName,
      jobPath:   jobPath || undefined,
      onFailure,
      params:    Object.keys(finalParams).length ? finalParams : undefined,
    })
    onClose()
  }

  const configFields = CONFIG_FIELDS[d.nodeType]

  // ── Bouton Parcourir réutilisable ─────────────────────────────────────────
  const browseBtn = (browseType: 'file' | 'directory' | 'save_file', ext: string, onResult: (p: string) => void) => (
    <button
      disabled={browsing}
      onClick={async () => {
        setBrowsing(true)
        try {
          const res = await api.system.browse(browseType, ext)
          if (res.path) onResult(res.path)
        } finally { setBrowsing(false) }
      }}
      style={{
        padding: '8px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600,
        border: '1px solid var(--bg-border)', background: 'var(--bg-hover)',
        color: 'var(--text-secondary)', cursor: browsing ? 'wait' : 'pointer',
        whiteSpace: 'nowrap', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4,
      }}
    >
      <FolderOpen size={12} /> {browsing ? '...' : 'Parcourir'}
    </button>
  )

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
      }}
    >
      <div style={{
        width: (d.nodeType === 'job' && jobMode === 'new') ? 640 : 520, maxHeight: '85vh',
        background: 'var(--bg-card)', borderRadius: 16,
        border: '1px solid var(--bg-border)',
        boxShadow: '0 32px 80px rgba(0,0,0,0.65)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 14,
          padding: '16px 20px', borderBottom: '1px solid var(--bg-border)', flexShrink: 0,
        }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: `${accent}22`,
          }}>
            <Icon size={20} style={{ color: accent }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                {def?.label ?? d.nodeType}
              </h2>
              <span style={{
                fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 20,
                background: `${accent}22`, color: accent, textTransform: 'uppercase',
              }}>
                {def?.category ?? 'node'}
              </span>
            </div>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {def?.description}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 28, borderRadius: 8,
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', flexShrink: 0,
            }}
          >
            <X size={15} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

          {/* Step name */}
          <label style={{ display: 'block', marginBottom: 14 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Step name
            </span>
            <input
              value={stepName}
              onChange={e => setStepName(e.target.value)}
              placeholder={d.stepName ?? d.nodeType}
              style={{
                display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
              }}
            />
          </label>

          {/* Job path (nœuds workflow job) */}
          {d.nodeType === 'job' && (() => {
            const btnStyle = (active: boolean) => ({
              flex: 1, padding: '6px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              borderRadius: 6, border: 'none',
              background: active ? 'var(--primary)' : 'transparent',
              color: active ? '#fff' : 'var(--text-muted)',
              transition: 'all .15s',
            })
            return (
              <div style={{ marginBottom: 14 }}>
                {/* Toggle */}
                <div style={{ display: 'flex', gap: 4, marginBottom: 12, background: 'var(--bg-hover)', borderRadius: 8, padding: 4 }}>
                  <button style={btnStyle(jobMode === 'existing')}
                    onClick={() => setJobMode('existing')}>
                    📂 Dossier existant
                  </button>
                  <button style={btnStyle(jobMode === 'new')}
                    onClick={() => setJobMode('new')}>
                    ✨ Créer nouveau
                  </button>
                </div>

                {jobMode === 'existing' && (
                  <label style={{ display: 'block' }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Job path
                    </span>
                    <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                      <input
                        value={jobPath}
                        onChange={e => setJobPath(e.target.value)}
                        placeholder="D:\monprojet\jobs\mon_job"
                        style={{
                          flex: 1, boxSizing: 'border-box',
                          background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                          borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                        }}
                      />
                      {browseBtn('directory', '', p => setJobPath(p))}
                    </div>
                  </label>
                )}

                {jobMode === 'new' && (
                  <JobCreatorWizard
                    defaultJobName={stepName || ''}
                    onCreated={(path) => {
                      setJobPath(path)
                      setJobMode('existing')
                    }}
                    onCancel={() => setJobMode('existing')}
                  />
                )}
              </div>
            )
          })()}

          {/* On failure (actions) */}
          {def?.category === 'action' && (
            <label style={{ display: 'block', marginBottom: 14 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                On failure
              </span>
              <select
                value={onFailure}
                onChange={e => setOnFailure(e.target.value as 'fail' | 'skip' | 'continue')}
                style={{
                  display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                  borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none', cursor: 'pointer',
                }}
              >
                <option value="fail">fail (default)</option>
                <option value="skip">skip</option>
                <option value="continue">continue</option>
              </select>
            </label>
          )}

          {/* Python — toggle inline / fichier (mutuellement exclusifs) */}
          {d.nodeType === 'action_python' && (() => {
            const btnStyle = (active: boolean) => ({
              flex: 1, padding: '6px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              borderRadius: 6, border: 'none',
              background: active ? accent : 'transparent',
              color: active ? '#fff' : 'var(--text-muted)',
              transition: 'all .15s',
            })
            return (
              <>
                {/* Toggle */}
                <div style={{ display: 'flex', gap: 4, marginBottom: 14, background: 'var(--bg-hover)', borderRadius: 8, padding: 4 }}>
                  <button style={btnStyle(pythonMode === 'inline')}
                    onClick={() => { setPythonMode('inline'); setParam('file_path', '') }}>
                    ✏️ Script inline
                  </button>
                  <button style={btnStyle(pythonMode === 'file')}
                    onClick={() => { setPythonMode('file'); setParam('script', '') }}>
                    📄 Fichier .py
                  </button>
                </div>

                {/* Script inline */}
                {pythonMode === 'inline' && (
                  <label style={{ display: 'block', marginBottom: 14 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Script Python <span style={{ color: 'var(--error)' }}>*</span>
                    </span>
                    <textarea
                      value={params.script ?? ''}
                      onChange={e => setParam('script', e.target.value)}
                      placeholder={'import sys\nprint(sys.version)'}
                      rows={8}
                      style={{
                        display: 'block', width: '100%', marginTop: 6, resize: 'vertical', boxSizing: 'border-box',
                        background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                        borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)',
                        fontSize: 12, fontFamily: 'monospace', outline: 'none', tabSize: 4,
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Tab') {
                          e.preventDefault()
                          const el = e.currentTarget
                          const s = el.selectionStart, end = el.selectionEnd
                          const val = el.value
                          const newVal = val.slice(0, s) + '    ' + val.slice(end)
                          setParam('script', newVal)
                          requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 4 })
                        }
                      }}
                    />
                  </label>
                )}

                {/* Chemin fichier .py */}
                {pythonMode === 'file' && (
                  <label style={{ display: 'block', marginBottom: 14 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Chemin fichier .py <span style={{ color: 'var(--error)' }}>*</span>
                    </span>
                    <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                      <input
                        value={params.file_path ?? ''}
                        onChange={e => setParam('file_path', e.target.value)}
                        placeholder="/home/user/script.py"
                        style={{
                          flex: 1, boxSizing: 'border-box',
                          background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                          borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                        }}
                      />
                      {browseBtn('file', '.py', p => setParam('file_path', p))}
                    </div>
                  </label>
                )}

                {/* Champs communs : working_dir + timeout */}
                {(['working_dir', 'timeout'] as const).map(key => {
                  const f = configFields?.find(x => x.key === key)
                  if (!f) return null
                  return (
                    <label key={key} style={{ display: 'block', marginBottom: 14 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {f.label}
                      </span>
                      {f.browseType ? (
                        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                          <input
                            type="text"
                            value={params[key] ?? ''}
                            onChange={e => setParam(key, e.target.value)}
                            placeholder={f.placeholder}
                            style={{
                              flex: 1, boxSizing: 'border-box',
                              background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                              borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                            }}
                          />
                          {browseBtn(f.browseType, f.browseExt ?? '', p => setParam(key, p))}
                        </div>
                      ) : (
                        <input
                          type={f.type === 'number' ? 'number' : 'text'}
                          value={params[key] ?? ''}
                          onChange={e => setParam(key, e.target.value)}
                          placeholder={f.placeholder}
                          style={{
                            display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                            background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                            borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                          }}
                        />
                      )}
                    </label>
                  )
                })}
              </>
            )
          })()}

          {/* Source DB — toggle mutuellement exclusif Table / Requête SQL */}
          {isDbSource && (() => {
            const btnStyle = (active: boolean) => ({
              flex: 1, padding: '6px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              borderRadius: 6, border: 'none',
              background: active ? accent : 'transparent',
              color: active ? '#fff' : 'var(--text-muted)',
              transition: 'all .15s',
            })
            return (
              <div style={{ marginBottom: 14 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Source des données
                </span>
                <div style={{ display: 'flex', gap: 4, margin: '6px 0 12px', background: 'var(--bg-hover)', borderRadius: 8, padding: 4 }}>
                  <button style={btnStyle(sourceMode === 'table')}
                    onClick={() => { setSourceMode('table'); setParam('query', '') }}>
                    🗂 Table
                  </button>
                  <button style={btnStyle(sourceMode === 'query')}
                    onClick={() => { setSourceMode('query'); setParam('table', '') }}>
                    🧮 Requête SQL
                  </button>
                </div>

                {sourceMode === 'table' ? (
                  <label style={{ display: 'block' }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Table <span style={{ color: 'var(--error)' }}>*</span>
                    </span>
                    <input
                      type="text"
                      value={params.table ?? ''}
                      onChange={e => setParam('table', e.target.value)}
                      placeholder="employees"
                      style={{
                        display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                        background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                        borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                      }}
                    />
                  </label>
                ) : (
                  <label style={{ display: 'block' }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Requête SQL <span style={{ color: 'var(--error)' }}>*</span>
                    </span>
                    <textarea
                      value={params.query ?? ''}
                      onChange={e => setParam('query', e.target.value)}
                      placeholder="SELECT * FROM employees WHERE age > 30"
                      rows={4}
                      style={{
                        display: 'block', width: '100%', marginTop: 6, resize: 'vertical', boxSizing: 'border-box',
                        background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                        borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)',
                        fontSize: 12, fontFamily: 'monospace', outline: 'none',
                      }}
                    />
                  </label>
                )}
              </div>
            )
          })()}

          {/* Source de droite pour le noeud join (choisie parmi les sources du canvas) */}
          {d.nodeType === 'transform_join' && (
            <label style={{ display: 'block', marginBottom: 14 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Source de droite <span style={{ color: 'var(--error)' }}>*</span>
              </span>
              <select
                value={params.rightSourceId ?? ''}
                onChange={e => setParam('rightSourceId', e.target.value)}
                style={{
                  display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                  borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none', cursor: 'pointer',
                }}
              >
                <option value="">- choisir une source -</option>
                {joinSources.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
              <span style={{ display: 'block', marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                L'autre source connectee devient le flux de gauche.
              </span>
            </label>
          )}

          {/* Join — choix mutuellement exclusif : cle commune vs cles distinctes (self-join) */}
          {d.nodeType === 'transform_join' && (() => {
            const btnStyle = (active: boolean) => ({
              flex: 1, padding: '6px 0', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              borderRadius: 6, border: 'none',
              background: active ? accent : 'transparent',
              color: active ? '#fff' : 'var(--text-muted)',
              transition: 'all .15s',
            })
            const inputStyle: React.CSSProperties = {
              display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
              background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
              borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
            }
            const lbl: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }
            return (
              <div style={{ marginBottom: 14 }}>
                <span style={lbl}>Correspondance</span>
                <div style={{ display: 'flex', gap: 4, margin: '6px 0 12px', background: 'var(--bg-hover)', borderRadius: 8, padding: 4 }}>
                  <button style={btnStyle(joinMode === 'common')}
                    onClick={() => { setJoinMode('common'); setParam('left_key', ''); setParam('right_key', '') }}>
                    🔑 Clé commune
                  </button>
                  <button style={btnStyle(joinMode === 'distinct')}
                    onClick={() => { setJoinMode('distinct'); setParam('key', '') }}>
                    ⇄ Clés distinctes (self-join)
                  </button>
                </div>

                {joinMode === 'common' ? (
                  <label style={{ display: 'block' }}>
                    <span style={lbl}>Clé de jointure <span style={{ color: 'var(--error)' }}>*</span></span>
                    <input type="text" value={params.key ?? ''} onChange={e => setParam('key', e.target.value)} placeholder="email" style={inputStyle} />
                  </label>
                ) : (
                  <>
                    <label style={{ display: 'block', marginBottom: 10 }}>
                      <span style={lbl}>Clé gauche — flux principal <span style={{ color: 'var(--error)' }}>*</span></span>
                      <input type="text" value={params.left_key ?? ''} onChange={e => setParam('left_key', e.target.value)} placeholder="manager_id" style={inputStyle} />
                    </label>
                    <label style={{ display: 'block' }}>
                      <span style={lbl}>Clé droite — source de droite <span style={{ color: 'var(--error)' }}>*</span></span>
                      <input type="text" value={params.right_key ?? ''} onChange={e => setParam('right_key', e.target.value)} placeholder="id" style={inputStyle} />
                    </label>
                  </>
                )}
              </div>
            )
          })()}

          {/* Champs spécifiques au type (tous sauf Python géré ci-dessus) */}
          {d.nodeType !== 'action_python' && configFields?.map(field => {
            // Sources DB : table & query sont gérés par le toggle ci-dessus
            if (isDbSource && (field.key === 'table' || field.key === 'query')) return null
            // Join : cle / left_key / right_key sont geres par le toggle ci-dessus
            if (d.nodeType === 'transform_join' && (field.key === 'key' || field.key === 'left_key' || field.key === 'right_key')) return null
            return (
            <label key={field.key} style={{ display: 'block', marginBottom: 14 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {field.label}{field.required && <span style={{ color: 'var(--error)', marginLeft: 3 }}>*</span>}
              </span>
              {field.type === 'password' ? (
                <div style={{ position: 'relative', marginTop: 6 }}>
                  <input
                    type={revealed[field.key] ? 'text' : 'password'}
                    value={params[field.key] ?? ''}
                    onChange={e => setParam(field.key, e.target.value)}
                    placeholder={field.placeholder}
                    autoComplete="new-password"
                    style={{
                      display: 'block', width: '100%', boxSizing: 'border-box',
                      background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                      borderRadius: 8, padding: '8px 40px 8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setRevealed(r => ({ ...r, [field.key]: !r[field.key] }))}
                    title={revealed[field.key] ? 'Masquer' : 'Afficher'}
                    style={{
                      position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4,
                    }}
                  >
                    {revealed[field.key] ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              ) : field.type === 'textarea' ? (
                <textarea
                  value={params[field.key] ?? ''}
                  onChange={e => setParam(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  rows={4}
                  style={{
                    display: 'block', width: '100%', marginTop: 6, resize: 'vertical', boxSizing: 'border-box',
                    background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                    borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)',
                    fontSize: 12, fontFamily: 'monospace', outline: 'none',
                  }}
                />
              ) : field.type === 'select' ? (
                <select
                  value={params[field.key] ?? (field.options?.[0] ?? '')}
                  onChange={e => setParam(field.key, e.target.value)}
                  style={{
                    display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                    background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                    borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none', cursor: 'pointer',
                  }}
                >
                  {field.options?.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : field.browseType ? (
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <input
                    type="text"
                    value={params[field.key] ?? ''}
                    onChange={e => setParam(field.key, e.target.value)}
                    placeholder={field.placeholder}
                    style={{
                      flex: 1, boxSizing: 'border-box',
                      background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                      borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                    }}
                  />
                  {browseBtn(field.browseType, field.browseExt ?? '', p => setParam(field.key, p))}
                </div>
              ) : (d.nodeType === 'transform_derive' && field.key === 'expr') ? (
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <input
                    type="text"
                    value={params[field.key] ?? ''}
                    onChange={e => setParam(field.key, e.target.value)}
                    placeholder={field.placeholder}
                    style={{ flex: 1, boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none' }}
                  />
                  <button type="button" onClick={() => setShowExprBuilder(true)} title="Assistant d'expression"
                    style={{ padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 800, fontStyle: 'italic', border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: accent, cursor: 'pointer', flexShrink: 0 }}>fx</button>
                </div>
              ) : (
                <input
                  type={field.type === 'number' ? 'number' : 'text'}
                  value={params[field.key] ?? ''}
                  onChange={e => setParam(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  style={{
                    display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                    background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                    borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
                  }}
                />
              )}
            </label>
            )
          })}

          {showExprBuilder && (
            <ExpressionBuilder
              initialExpr={params.expr ?? ''}
              accent={accent}
              onApply={(ex) => { setParam('expr', ex); setShowExprBuilder(false) }}
              onClose={() => setShowExprBuilder(false)}
            />
          )}

          {/* Node ID */}
          <label style={{ display: 'block', marginTop: 4 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Node ID
            </span>
            <input
              readOnly value={node.id}
              style={{
                display: 'block', width: '100%', marginTop: 6, boxSizing: 'border-box',
                background: 'var(--bg-hover)', border: '1px solid var(--bg-border)',
                borderRadius: 8, padding: '8px 12px', color: 'var(--text-muted)',
                fontSize: 12, fontFamily: 'monospace', outline: 'none',
              }}
            />
          </label>

        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 10,
          padding: '14px 20px', borderTop: '1px solid var(--bg-border)', flexShrink: 0,
        }}>
          <button onClick={onClose} style={{
            padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
            background: 'transparent', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)',
          }}>
            Cancel
          </button>
          <button onClick={handleSave} style={{
            padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
            background: 'var(--primary)', border: 'none', color: '#fff',
          }}>
            Save
          </button>
        </div>
      </div>
    </div>
  )
}


