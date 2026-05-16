import { useEffect, useRef } from 'react'

interface Props {
  open: boolean
  onToggle: (open: boolean) => void
}

export function IdeateButton({ open, onToggle }: Props) {
  const isMountedRef = useRef(false)

  // Sync the URL hash on toggle so a refresh reopens the drawer + the URL is shareable.
  // Skip the first effect run on mount so the Mount effect (below) gets to honor an inbound #ideate hash.
  useEffect(() => {
    if (!isMountedRef.current) return
    const target = open ? '#ideate' : ''
    if (window.location.hash !== target) {
      // Use replaceState so toggling doesn't pollute browser history.
      const url = window.location.pathname + window.location.search + target
      window.history.replaceState(null, '', url)
    }
  }, [open])

  // On mount, honor an inbound #ideate hash. Runs AFTER the sync effect, so the
  // sync effect's skip-on-first-render guard preserves the hash for us to read.
  useEffect(() => {
    if (window.location.hash === '#ideate' && !open) {
      onToggle(true)
    }
    isMountedRef.current = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <button
      type="button"
      onClick={() => onToggle(!open)}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors ${
        open
          ? 'border-slate-400 bg-slate-100 text-slate-900'
          : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
      }`}
      aria-pressed={open}
      aria-label="Ideate"
    >
      <span aria-hidden>💡</span>
      <span>Ideate</span>
    </button>
  )
}
