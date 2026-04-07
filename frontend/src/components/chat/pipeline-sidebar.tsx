import { useNavigate } from 'react-router-dom'
import { useChatStore } from '../../stores/chat-store'
import { PIPELINE_PHASES } from '../../types/proposal'
import type { Proposal } from '../../types/proposal'

interface Props {
  proposal: Proposal
  clientName?: string
}

export function PipelineSidebar({ proposal, clientName }: Props) {
  const navigate = useNavigate()
  const pipelinePhase = useChatStore((s) => s.pipelinePhase)
  const completedPhases = proposal.pipeline_state?.phases_completed || []

  return (
    <aside className="w-72 border-r border-stone-200 bg-white flex flex-col flex-shrink-0 h-full overflow-y-auto">
      <div className="p-5 border-b border-stone-100">
        <button
          onClick={() => navigate('/proposals')}
          className="text-xs text-stone-400 hover:text-stone-600 mb-3"
        >
          &larr; All proposals
        </button>
        <h2 className="text-base font-semibold text-stone-900 truncate">{proposal.project_name}</h2>
        {clientName && <p className="text-sm text-stone-500 mt-0.5">{clientName}</p>}
        <span className="mt-2 inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 capitalize">
          {proposal.status}
        </span>
      </div>

      <div className="p-5">
        <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-3">
          Pipeline
        </h3>
        <div className="space-y-1">
          {PIPELINE_PHASES.map((phase) => {
            const isCurrent = pipelinePhase === phase.key
            const isCompleted = completedPhases.includes(phase.key)

            return (
              <div key={phase.key} className="flex items-center gap-3 py-1.5">
                {/* Status indicator */}
                <div className="flex-shrink-0">
                  {isCompleted ? (
                    <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  ) : isCurrent ? (
                    <div className="w-5 h-5 rounded-full bg-stone-900 flex items-center justify-center">
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-stone-200" />
                  )}
                </div>

                {/* Label */}
                <span
                  className={`text-sm ${
                    isCurrent
                      ? 'font-medium text-stone-900'
                      : isCompleted
                        ? 'text-stone-600'
                        : 'text-stone-400'
                  }`}
                >
                  {phase.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
