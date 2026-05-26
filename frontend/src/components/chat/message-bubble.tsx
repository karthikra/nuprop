import type { ChatMessage } from '../../types/proposal'
import { ApprovalGate } from './approval-gate'
import { CostModelCard } from './cost-model-card'
import { OutputReadyCard } from './output-ready-card'
import { ResearchPlanCard } from './research-plan-card'
import { ResearchActivityLog } from './research-activity-log'
import { ResearchFindingsCard } from './research-findings-card'

interface Props {
  message: ChatMessage
  proposalId: string
}

export function MessageBubble({ message, proposalId }: Props) {
  if (message.role === 'system') {
    return (
      <div className="flex justify-center">
        <p className="text-xs text-stone-400 bg-stone-100 rounded-full px-3 py-1">
          {message.content}
        </p>
      </div>
    )
  }

  const isUser = message.role === 'user'
  const extra = message.extra_data as Record<string, unknown>

  // Brief summary with approval gate
  if (message.message_type === 'brief_summary' && extra?.requires_approval) {
    return (
      <div className="flex justify-start">
        <ApprovalGate message={message} proposalId={proposalId} gateId="brief" />
      </div>
    )
  }

  // Template or other approval gates
  if (message.message_type === 'approval_gate' && extra?.requires_approval) {
    const gateType = (extra.gate_type as string) || 'unknown'
    return (
      <div className="flex justify-start">
        <ApprovalGate message={message} proposalId={proposalId} gateId={gateType} />
      </div>
    )
  }

  // Research / benchmarks plan cards
  if (
    message.message_type === 'research_plan' ||
    message.message_type === 'benchmarks_plan'
  ) {
    return <ResearchPlanCard message={message} />
  }

  // Research / benchmarks activity logs
  if (
    message.message_type === 'research_activity_log' ||
    message.message_type === 'benchmarks_activity_log'
  ) {
    return <ResearchActivityLog message={message} />
  }

  // Research / benchmarks findings cards
  if (
    message.message_type === 'research_findings' ||
    message.message_type === 'benchmarks_findings'
  ) {
    return <ResearchFindingsCard message={message} />
  }

  // Cost model — interactive table
  if (message.message_type === 'cost_model' && extra?.requires_approval) {
    return <CostModelCard message={message} proposalId={proposalId} />
  }

  // Output ready — download files
  if (message.message_type === 'output_ready') {
    return <OutputReadyCard message={message} proposalId={proposalId} />
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-stone-900 text-white rounded-br-md'
            : 'bg-white border border-stone-200 text-stone-800 rounded-bl-md'
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        <p className={`mt-1 text-[10px] ${isUser ? 'text-stone-400' : 'text-stone-400'}`}>
          {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-stone-200 rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-stone-400 animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 rounded-full bg-stone-400 animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 rounded-full bg-stone-400 animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}

export function ProgressTracker({ items }: { items: { agent: string; status: string; detail: string }[] }) {
  if (items.length === 0) return null

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] rounded-2xl border border-stone-200 bg-white px-4 py-3 space-y-2">
        {items.map((item) => (
          <div key={item.agent} className="flex items-center gap-2 text-sm">
            {item.status === 'complete' ? (
              <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : item.status === 'error' ? (
              <svg className="w-4 h-4 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <div className="w-4 h-4 flex-shrink-0">
                <div className="w-3 h-3 border-2 border-stone-400 border-t-stone-900 rounded-full animate-spin" />
              </div>
            )}
            <span className={item.status === 'complete' ? 'text-stone-600' : 'text-stone-900'}>
              {item.detail}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
