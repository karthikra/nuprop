import { useState } from 'react'
import { api } from '../../api/client'
import type { ChatMessage } from '../../types/proposal'

interface Props {
  message: ChatMessage
  proposalId: string
  gateId: string
}

export function ApprovalGate({ message, proposalId, gateId }: Props) {
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const extra = message.extra_data as Record<string, unknown>

  const handleApprove = async () => {
    setApproving(true)
    try {
      const data: Record<string, unknown> = {}
      if (gateId === 'template' && extra?.template_key) {
        data.template_key = extra.template_key
      }
      await api.post(`/chat/${proposalId}/approve/${gateId}`, { data })
      setApproved(true)
    } catch (err) {
      console.error('Approval failed:', err)
    }
    setApproving(false)
  }

  const isTemplate = extra?.gate_type === 'template'
  const isBrief = gateId === 'brief'
  const brief = isBrief ? (extra?.brief as Record<string, unknown>) : undefined

  return (
    <div className="max-w-[85%] rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-5 h-5 rounded-full bg-amber-400 flex items-center justify-center">
          <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <span className="text-sm font-semibold text-amber-900">
          {isTemplate ? 'Template Selection' : 'Brief Summary'} — Review & Approve
        </span>
      </div>

      <p className="text-sm text-amber-800 leading-relaxed whitespace-pre-wrap">{message.content}</p>

      {brief && (
        <div className="mt-3 rounded-lg bg-white/70 border border-amber-200 p-3 text-xs text-stone-700 font-mono overflow-x-auto max-h-60 overflow-y-auto">
          <pre>{JSON.stringify(brief, null, 2)}</pre>
        </div>
      )}

      {isTemplate && typeof extra?.confidence === 'number' && (
        <div className="mt-2 text-xs text-amber-700">
          Confidence: {Math.round(extra.confidence * 100)}%
        </div>
      )}

      {!approved ? (
        <div className="mt-4 flex gap-2">
          <button
            onClick={handleApprove}
            disabled={approving}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {approving ? 'Processing...' : isTemplate ? 'Confirm Template' : 'Approve Brief'}
          </button>
          <button
            disabled={approving}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            Adjust
          </button>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Approved — advancing to next phase
        </div>
      )}
    </div>
  )
}
