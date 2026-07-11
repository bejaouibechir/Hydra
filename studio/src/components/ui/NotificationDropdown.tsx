/**
 * components/ui/NotificationDropdown.tsx
 * Cloche de notifications avec dropdown.
 */
import { useRef, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, X, Trash2 } from 'lucide-react'
import { useNotifications, NotifType } from '@/contexts/NotificationContext'

function notifDot(type: NotifType) {
  return { success: 'var(--success)', error: 'var(--error)', warning: 'var(--warning)', info: 'var(--info)' }[type]
}

function timeAgo(date: Date) {
  const s = Math.floor((Date.now() - date.getTime()) / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  return `${Math.floor(m / 60)}h`
}

export default function NotificationDropdown() {
  const { notifications, unreadCount, markAllRead, remove, clear } = useNotifications()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  const toggle = () => {
    setOpen(v => {
      if (!v && unreadCount > 0) markAllRead()
      return !v
    })
  }

  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost p-2 !gap-0 relative" title="Notifications" onClick={toggle}>
        <Bell size={16} />
        {unreadCount > 0 && (
          <span
            className="absolute top-1 right-1 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center text-white"
            style={{ background: 'var(--error)' }}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-80 rounded-xl shadow-2xl z-50 overflow-hidden"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--bg-border)' }}
          >
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Notifications
            </span>
            {notifications.length > 0 && (
              <button onClick={clear} className="btn-ghost !px-2 !py-1 text-xs !gap-1">
                <Trash2 size={12} /> Tout effacer
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-72 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="text-center text-sm py-8" style={{ color: 'var(--text-muted)' }}>
                Aucune notification
              </p>
            ) : (
              notifications.map((n, i) => (
                <div
                  key={n.id}
                  className="flex items-start gap-3 px-4 py-3"
                  title={n.link ? 'Double-clic : ouvrir l\'élément concerné' : undefined}
                  onDoubleClick={() => { if (n.link) { setOpen(false); navigate(n.link) } }}
                  style={{
                    borderBottom: i < notifications.length - 1 ? '1px solid var(--bg-border)' : 'none',
                    background: n.read ? 'transparent' : 'var(--primary-subtle)',
                    cursor: n.link ? 'pointer' : 'default',
                  }}
                >
                  <div
                    className="w-2 h-2 rounded-full shrink-0 mt-1.5"
                    style={{ background: notifDot(n.type) }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                      {n.title}
                    </p>
                    {n.message && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-secondary)' }}>
                        {n.message}
                      </p>
                    )}
                    <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                      {timeAgo(n.timestamp)}
                    </p>
                  </div>
                  <button onClick={() => remove(n.id)} className="btn-ghost !p-1 !gap-0 shrink-0">
                    <X size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
