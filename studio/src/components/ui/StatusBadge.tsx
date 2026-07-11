import clsx from 'clsx'

type Status = 'success' | 'failed' | 'running' | 'pending' | 'published' | 'draft'

const MAP: Record<Status, string> = {
  success:   'badge-success',
  failed:    'badge-error',
  running:   'badge-info',
  pending:   'badge-pending',
  published: 'badge-success',
  draft:     'badge-warning',
}
const LABELS: Record<Status, string> = {
  success: 'Success', failed: 'Failed', running: 'Running',
  pending: 'Pending', published: 'Published', draft: 'Draft',
}

export default function StatusBadge({ status }: { status: Status }) {
  return <span className={clsx(MAP[status] ?? 'badge-pending')}>{LABELS[status] ?? status}</span>
}
