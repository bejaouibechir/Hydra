/**
 * contexts/NotificationContext.tsx
 * Système de notifications in-memory (ephémère par session).
 */
import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

export type NotifType = 'success' | 'error' | 'info' | 'warning'

export interface Notification {
  id: string
  type: NotifType
  title: string
  message?: string
  timestamp: Date
  read: boolean
  link?: string        // cible de navigation (double-clic) — ex: éditeur sur le job en échec
}

interface NotifCtx {
  notifications: Notification[]
  unreadCount: number
  add: (type: NotifType, title: string, message?: string, link?: string) => void
  markAllRead: () => void
  remove: (id: string) => void
  clear: () => void
}

const Ctx = createContext<NotifCtx | null>(null)

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])

  const add = useCallback((type: NotifType, title: string, message?: string, link?: string) => {
    const notif: Notification = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      type, title, message, link,
      timestamp: new Date(),
      read: false,
    }
    setNotifications(prev => [notif, ...prev].slice(0, 50))
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
  }, [])

  const remove = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const clear = useCallback(() => setNotifications([]), [])

  const unreadCount = notifications.filter(n => !n.read).length

  return (
    <Ctx.Provider value={{ notifications, unreadCount, add, markAllRead, remove, clear }}>
      {children}
    </Ctx.Provider>
  )
}

export function useNotifications() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider')
  return ctx
}
