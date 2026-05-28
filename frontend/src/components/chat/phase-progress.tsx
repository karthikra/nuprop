import { useEffect, useState } from 'react'
import { useChatStore } from '../../stores/chat-store'
import { useRetryPhase } from '../../api/proposals'

interface Props {
  proposalId: string
}

/** ARQ job name → friendly label. These are job names, not user-facing
 * pipeline phases — do NOT reuse PIPELINE_PHASES (different key space). */
const JOB_LABELS: Record<string, string> = {
  analyze_brief: 'Brief',
  run_research: 'Research',
  run_benchmarks: 'Benchmarks',
  build_cost_model: 'Cost Model',
  generate_sections: 'Sections',
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Sticky, compact status bar pinned to the top of the chat scroll area.
 * Mirrors a single ARQ job's lifecycle (queued → running → complete/failed)
 * and surfaces a Retry action when the phase fails. */
export function PhaseProgress({ proposalId }: Props) {
  const jobStatus = useChatStore((s) => s.jobStatus)
  const retry = useRetryPhase(proposalId)
  const [now, setNow] = useState(() => Date.now())

  const isRunning = jobStatus?.state === 'running'
  const startedAt = jobStatus?.updated_at

  // Live elapsed timer — only ticks while the job is running and we have an
  // anchor timestamp. Cleared on unmount or when state leaves "running".
  useEffect(() => {
    if (!isRunning || !startedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [isRunning, startedAt])

  if (jobStatus == null) return null

  const label = JOB_LABELS[jobStatus.phase] ?? jobStatus.phase.replace(/_/g, ' ')

  const elapsed =
    isRunning && startedAt
      ? formatElapsed(Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000)))
      : null

  return (
    <div className="sticky top-0 z-10 -mx-6 -mt-4 mb-2 px-6 py-2 bg-white/95 backdrop-blur border-b border-stone-200 flex items-center gap-3 text-sm">
      <span className="font-medium text-stone-900">{label}</span>

      {jobStatus.state === 'queued' && (
        <span className="flex items-center gap-1.5 text-stone-500">
          <span className="w-2 h-2 rounded-full bg-stone-300" />
          Queued
        </span>
      )}

      {jobStatus.state === 'running' && (
        <span className="flex items-center gap-1.5 text-stone-700">
          <span className="w-3 h-3 border-2 border-stone-400 border-t-stone-900 rounded-full animate-spin" />
          Running
          {elapsed && <span className="tabular-nums text-stone-500">{elapsed}</span>}
        </span>
      )}

      {jobStatus.state === 'complete' && (
        <span className="flex items-center gap-1.5 text-stone-600">
          <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Complete
        </span>
      )}

      {jobStatus.state === 'failed' && (
        <span className="flex items-center gap-2 min-w-0 text-stone-700">
          <svg className="w-4 h-4 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          <span className="text-red-500">Failed</span>
          {jobStatus.error && (
            <span className="truncate text-stone-500">{jobStatus.error}</span>
          )}
          <button
            type="button"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
            className="ml-auto flex-shrink-0 rounded-md border border-stone-300 px-2.5 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {retry.isPending ? 'Retrying…' : 'Retry'}
          </button>
        </span>
      )}
    </div>
  )
}
