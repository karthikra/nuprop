import { useState, useRef, useEffect } from 'react'
import { useAuthStore } from '../../stores/auth-store'
import { useUnreadCount } from '../../api/notifications'
import { NotificationDropdown } from './notification-dropdown'

export function Nav() {
  const agency = useAuthStore((s) => s.agency)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { data: unreadCount } = useUnreadCount()
  const [showNotifications, setShowNotifications] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowNotifications(false)
      }
    }
    if (showNotifications) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [showNotifications])

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 border-b border-stone-200 bg-white px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-lg font-semibold tracking-tight text-stone-900">
          NUPROP
        </span>
        {agency && (
          <>
            <span className="text-stone-300">/</span>
            <span className="text-sm font-medium text-stone-600">{agency.name}</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg hover:bg-stone-100 text-stone-500"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
            {(unreadCount ?? 0) > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                {unreadCount! > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
          {showNotifications && (
            <NotificationDropdown onClose={() => setShowNotifications(false)} />
          )}
        </div>

        {/* User */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-xs font-medium flex items-center justify-center">
            {user?.full_name?.[0]?.toUpperCase() || '?'}
          </div>
          <button
            onClick={logout}
            className="text-xs text-stone-400 hover:text-stone-600"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}
