import React from 'react'

interface Props {
  icon: React.ReactNode | React.ElementType
  title: string
  description?: string
  action?: React.ReactNode
}

export default function EmptyState({ icon, title, description, action }: Props) {
  // Un élément React déjà construit est rendu tel quel ; tout le reste
  // (fonction, forwardRef/memo lucide…) est instancié via createElement.
  const iconNode = React.isValidElement(icon)
    ? icon
    : icon != null
      ? React.createElement(icon as React.ElementType, { size: 24, style: { color: 'var(--text-muted)' } })
      : null
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
        {iconNode}
      </div>
      <h3 className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>{title}</h3>
      {description && <p className="text-sm mb-4 max-w-xs" style={{ color: 'var(--text-secondary)' }}>{description}</p>}
      {action}
    </div>
  )
}
