import { useState } from 'react'
import { api } from '../../api/client'
import type { ChatMessage } from '../../types/proposal'

interface ScopeSection {
  deliverable: string
  package_name: string
  content: string
}

interface NarrativeSections {
  covering_letter: string
  covering_letter_alt: string
  letter_strategy_primary: string
  letter_strategy_alt: string
  executive_summary: string
  scope_sections: ScopeSection[]
  cost_rationale: string | null
  terms: string
}

interface Props {
  message: ChatMessage
  proposalId: string
}

function SectionCard({ title, children, defaultOpen = false }: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-purple-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-purple-50 hover:bg-purple-100 transition-colors text-left"
      >
        <span className="text-sm font-medium text-purple-900">{title}</span>
        <svg
          className={`w-4 h-4 text-purple-500 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-4 py-3 text-sm text-stone-800 leading-relaxed whitespace-pre-wrap bg-white">
          {children}
        </div>
      )}
    </div>
  )
}

export function NarrativePreview({ message, proposalId }: Props) {
  const extra = message.extra_data as Record<string, unknown>
  const sections = extra?.sections as NarrativeSections | undefined
  const [selectedLetter, setSelectedLetter] = useState<'primary' | 'alt'>('primary')
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)

  if (!sections) return null

  const handleApprove = async () => {
    setApproving(true)
    try {
      await api.post(`/chat/${proposalId}/approve/narrative`, {
        data: { selected_letter: selectedLetter },
      })
      setApproved(true)
    } catch (err) {
      console.error('Approval failed:', err)
    }
    setApproving(false)
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full rounded-2xl border border-purple-200 bg-purple-50 px-5 py-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-5 h-5 rounded-full bg-purple-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-purple-900">Proposal Narrative — Review & Approve</span>
        </div>

        <p className="text-sm text-purple-800 mb-4">{message.content}</p>

        <div className="space-y-3">
          {/* Covering Letter — Tab Selector */}
          <div className="border border-purple-200 rounded-lg overflow-hidden">
            <div className="flex bg-purple-50">
              <button
                onClick={() => setSelectedLetter('primary')}
                className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                  selectedLetter === 'primary'
                    ? 'bg-purple-600 text-white'
                    : 'text-purple-700 hover:bg-purple-100'
                }`}
              >
                Letter — {sections.letter_strategy_primary}
                {selectedLetter === 'primary' && ' ✓'}
              </button>
              <button
                onClick={() => setSelectedLetter('alt')}
                className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                  selectedLetter === 'alt'
                    ? 'bg-purple-600 text-white'
                    : 'text-purple-700 hover:bg-purple-100'
                }`}
              >
                Letter — {sections.letter_strategy_alt}
                {selectedLetter === 'alt' && ' ✓'}
              </button>
            </div>
            <div className="px-4 py-3 text-sm text-stone-800 leading-relaxed whitespace-pre-wrap bg-white max-h-80 overflow-y-auto">
              {selectedLetter === 'primary' ? sections.covering_letter : sections.covering_letter_alt}
            </div>
          </div>

          {/* Executive Summary */}
          <SectionCard title="Executive Summary" defaultOpen>
            {sections.executive_summary}
          </SectionCard>

          {/* Scope Sections */}
          {sections.scope_sections.map((scope, i) => (
            <SectionCard key={i} title={`Scope: ${scope.deliverable}`}>
              {scope.content}
            </SectionCard>
          ))}

          {/* Cost Rationale */}
          {sections.cost_rationale && (
            <SectionCard title="Cost Rationale">
              {sections.cost_rationale}
            </SectionCard>
          )}

          {/* Terms */}
          <SectionCard title="Terms & Conditions">
            {sections.terms}
          </SectionCard>
        </div>

        {/* Approve */}
        {!approved ? (
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleApprove}
              disabled={approving}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {approving ? 'Approving...' : 'Approve & Generate Outputs'}
            </button>
            <span className="text-xs text-purple-600">
              Using {selectedLetter === 'primary' ? sections.letter_strategy_primary : sections.letter_strategy_alt} letter
            </span>
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Approved — generating final outputs
          </div>
        )}
      </div>
    </div>
  )
}
