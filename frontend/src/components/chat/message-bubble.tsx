import type { ChatMessage } from '../../types/proposal'
import { ApprovalGate } from './approval-gate'
import { CostModelCard } from './cost-model-card'
import { NarrativePreview } from './narrative-preview'
import { OutputReadyCard } from './output-ready-card'

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

  // Research findings — collapsible card
  if (message.message_type === 'research_findings') {
    return <ResearchCard content={message.content} />
  }

  // Cost model — interactive table
  if (message.message_type === 'cost_model' && extra?.requires_approval) {
    return <CostModelCard message={message} proposalId={proposalId} />
  }

  // Narrative preview — all sections with tabs + accordion
  if (message.message_type === 'narrative_preview' && extra?.requires_approval) {
    return <NarrativePreview message={message} proposalId={proposalId} />
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

function ResearchCard({ content }: { content: string }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-2xl border border-blue-200 bg-blue-50 px-5 py-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-blue-900">Research & Benchmarks Complete</span>
        </div>
        <div className="text-sm text-blue-800 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto prose prose-sm prose-blue">
          {content}
        </div>
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
