import { X } from 'lucide-react'
import { ReactNode } from 'react'

interface Props {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}

export default function Modal({ title, open, onClose, children, footer }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative rounded-xl w-full max-w-md shadow-2xl"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
        <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--bg-border)' }}>
          <h2 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{title}</h2>
          <button onClick={onClose} className="btn-ghost p-1 !gap-0"><X size={16} /></button>
        </div>
        <div className="p-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 p-4" style={{ borderTop: '1px solid var(--bg-border)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
