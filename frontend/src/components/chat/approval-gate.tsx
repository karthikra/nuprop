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

      {brief && <BriefDetails brief={brief} />}

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

// ── Brief summary card ─────────────────────────────────────────────────────

type RecordLike = Record<string, unknown>

function BriefDetails({ brief }: { brief: RecordLike }) {
  const client = (brief.client as RecordLike) ?? {}
  const project = (brief.project as RecordLike) ?? {}
  const context = (brief.context as RecordLike) ?? {}
  const contacts = (client.contacts as RecordLike[]) ?? []
  const deliverables = (project.deliverables as RecordLike[]) ?? []

  return (
    <div className="mt-3 rounded-lg bg-white/70 border border-amber-200 divide-y divide-amber-100 text-sm">
      <BriefSection title="Client">
        <Field label="Name" value={client.name} />
        <Field label="Industry" value={client.industry} />
        <Field label="Size" value={client.size} />
      </BriefSection>

      {contacts.length > 0 && (
        <BriefSection title="Contacts">
          <ul className="space-y-1">
            {contacts.map((c, i) => (
              <li key={i} className="text-stone-700">
                <span className="font-medium">{String(c.name ?? '—')}</span>
                {c.role ? <span className="text-stone-500"> — {String(c.role)}</span> : null}
                {c.relationship ? (
                  <span className="text-stone-400"> · {String(c.relationship)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </BriefSection>
      )}

      <BriefSection title="Project">
        <Field label="Type" value={project.type} />
        <Field label="Timeline" value={project.timeline} />
        <Field label="Budget" value={project.budget_signal} />
        {deliverables.length > 0 && (
          <div className="mt-2">
            <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Deliverables</p>
            <ul className="space-y-1">
              {deliverables.map((d, i) => (
                <li key={i} className="text-stone-700">
                  <span className="text-stone-400">•</span>{' '}
                  <span className="font-medium">{String(d.category ?? '—')}</span>
                  {d.details ? (
                    <span className="text-stone-500"> — {String(d.details)}</span>
                  ) : null}
                  {typeof d.quantity === 'number' && d.quantity > 1 ? (
                    <span className="text-stone-400"> (×{d.quantity})</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </BriefSection>

      <BriefSection title="Context">
        <Field label="Relationship" value={prettify(context.relationship)} />
        <Field label="Competition" value={context.competition} />
        <Field label="Urgency" value={context.urgency} />
        <Field label="Decision maker" value={context.decision_maker} />
      </BriefSection>

      <details className="px-3 py-2 text-xs text-stone-500">
        <summary className="cursor-pointer hover:text-stone-700 select-none">Raw JSON</summary>
        <pre className="mt-2 overflow-x-auto text-[10px] font-mono text-stone-600 whitespace-pre">
          {JSON.stringify(brief, null, 2)}
        </pre>
      </details>
    </div>
  )
}

function BriefSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider font-semibold text-amber-700 mb-1.5">
        {title}
      </p>
      {children}
    </div>
  )
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  const s = String(value).trim()
  if (!s) return null
  return (
    <p className="text-stone-700 leading-snug">
      <span className="text-[10px] uppercase tracking-wider text-stone-500 inline-block w-28 align-baseline">
        {label}
      </span>
      <span>{s}</span>
    </p>
  )
}

/** Turn snake_case enum-ish values like "cold_pitch" into "Cold pitch". */
function prettify(value: unknown): string | undefined {
  if (typeof value !== 'string' || !value) return undefined
  const t = value.trim()
  if (!t) return undefined
  const spaced = t.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
