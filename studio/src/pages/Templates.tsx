import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, Template } from '@/lib/api'
import Spinner from '@/components/ui/Spinner'
import EmptyState from '@/components/ui/EmptyState'
import { LayoutTemplate, Copy, Check, ChevronDown, ChevronRight } from 'lucide-react'

export default function Templates() {
  const { data, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => api.templates.list(),
  })

  const [openId, setOpenId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copy = async (t: Template) => {
    try {
      await navigator.clipboard.writeText(t.yaml_content)
      setCopiedId(t.id)
      setTimeout(() => setCopiedId(null), 1500)
    } catch {
      /* presse-papier indisponible — sans effet */
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Templates</h1>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {data?.length ?? 0} ready-to-use workflow templates
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner size="lg" /></div>
      ) : !data || data.length === 0 ? (
        <EmptyState
          icon={LayoutTemplate}
          title="No templates"
          description="Preconfigured workflow templates will appear here."
        />
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
          {data.map(t => {
            const open = openId === t.id
            return (
              <div
                key={t.id}
                className="rounded-xl overflow-hidden flex flex-col"
                style={{ border: '1px solid var(--bg-border)', background: 'var(--bg-card)' }}
              >
                <div className="p-4 flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <LayoutTemplate size={16} style={{ color: 'var(--primary)' }} />
                      <span className="font-medium text-sm">{t.name}</span>
                    </div>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
                      style={{ background: 'var(--primary-subtle)', color: 'var(--primary)' }}
                    >
                      {t.category}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {t.description}
                  </p>
                </div>

                <div
                  className="flex items-center gap-1 px-3 py-2 mt-auto"
                  style={{ borderTop: '1px solid var(--bg-border)' }}
                >
                  <button
                    onClick={() => setOpenId(open ? null : t.id)}
                    className="btn-ghost text-xs !px-2 !py-1 !gap-1"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    {open ? 'Hide YAML' : 'View YAML'}
                  </button>
                  <button
                    onClick={() => copy(t)}
                    className="btn-ghost text-xs !px-2 !py-1 !gap-1 ml-auto"
                    style={{ color: copiedId === t.id ? 'var(--success)' : 'var(--text-secondary)' }}
                    title="Copy YAML to clipboard"
                  >
                    {copiedId === t.id ? <Check size={13} /> : <Copy size={13} />}
                    {copiedId === t.id ? 'Copied' : 'Copy YAML'}
                  </button>
                </div>

                {open && (
                  <pre
                    className="text-xs font-mono p-3 overflow-auto"
                    style={{
                      maxHeight: 260,
                      background: 'var(--bg-code, var(--bg-app))',
                      color: 'var(--text-secondary)',
                      borderTop: '1px solid var(--bg-border)',
                      margin: 0,
                    }}
                  >
                    {t.yaml_content}
                  </pre>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
