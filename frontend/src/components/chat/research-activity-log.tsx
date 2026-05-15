import { useState, useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types/proposal'

interface Event {
  type: 'search' | 'read' | 'note'
  query?: string
  url?: string
  title?: string
  text?: string
  ts: string
}

interface Props {
  message: ChatMessage
}

export function ResearchActivityLog({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const status = (extra.status as string) ?? 'running'
  const events = (extra.events as Event[]) ?? []
  const error = extra.error as string | undefined
  const isRunning = status === 'running'
  const isComplete = status === 'complete'

  // Collapse-by-default on complete; always expanded on running or failed.
  const [collapsed, setCollapsed] = useState(isComplete)
  useEffect(() => { setCollapsed(isComplete) }, [isComplete])

  // Auto-scroll while running.
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (isRunning && typeof endRef.current?.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events.length, isRunning])

  const title = phase === 'benchmarks' ? '⚡ Benchmark activity' : '⚡ Research activity'
  const searchCount = events.filter((e) => e.type === 'search').length
  const readCount = events.filter((e) => e.type === 'read').length

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] w-[480px] rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <StatusBadge status={status} error={error} />
        </div>
        {isComplete && collapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="text-xs text-slate-600 hover:text-slate-900"
            aria-label="Expand activity log"
          >
            ✓ {searchCount} {searchCount === 1 ? 'search' : 'searches'} · {readCount} {readCount === 1 ? 'source' : 'sources'} · click to expand
          </button>
        ) : (
          <ol
            aria-live={isRunning ? 'polite' : 'off'}
            className="space-y-1 max-h-72 overflow-y-auto pr-1"
          >
            {events.map((e, i) => <EventRow key={i} event={e} />)}
            <div ref={endRef} />
          </ol>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status, error }: { status: string; error?: string }) {
  if (status === 'running') {
    return (
      <span aria-label="Running" className="flex items-center gap-1.5 text-xs text-slate-600">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
        running
      </span>
    )
  }
  if (status === 'complete') {
    return (
      <span aria-label="Complete" className="flex items-center gap-1.5 text-xs text-green-700">
        ✓ complete
      </span>
    )
  }
  return (
    <span
      aria-label="Failed"
      title={error || ''}
      className="flex items-center gap-1.5 text-xs text-amber-700"
    >
      ⚠ failed
    </span>
  )
}

function EventRow({ event }: { event: Event }) {
  const time = event.ts.slice(11, 19)
  if (event.type === 'search') {
    return (
      <li className="text-xs text-slate-700 flex gap-2">
        <span className="text-slate-400 tabular-nums">{time}</span>
        <span>🔍</span>
        <code className="font-mono text-slate-800">{event.query}</code>
      </li>
    )
  }
  if (event.type === 'read') {
    const domain = (() => { try { return new URL(event.url ?? '').hostname } catch { return '' } })()
    return (
      <li className="text-xs text-slate-700 flex gap-2">
        <span className="text-slate-400 tabular-nums">{time}</span>
        <span>📄</span>
        <span><strong>{domain}</strong> — {event.title}</span>
      </li>
    )
  }
  return (
    <li className="text-xs text-slate-600 flex gap-2 italic">
      <span className="text-slate-400 tabular-nums">{time}</span>
      <span>🧠</span>
      <span>{event.text}</span>
    </li>
  )
}
