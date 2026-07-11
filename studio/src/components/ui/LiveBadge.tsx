/** Badge "LIVE" avec pulsation — affiché quand un run est actif */
export default function LiveBadge({ label = 'LIVE' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full"
      style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--error)' }}>
      <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--error)' }} />
      {label}
    </span>
  )
}
