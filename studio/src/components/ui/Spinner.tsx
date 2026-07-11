import clsx from 'clsx'
export default function Spinner({ size = 'md', className }: { size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const s = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' }[size]
  return (
    <div className={clsx('animate-spin rounded-full border-2 border-surface-border border-t-hydra-500', s, className)} />
  )
}
