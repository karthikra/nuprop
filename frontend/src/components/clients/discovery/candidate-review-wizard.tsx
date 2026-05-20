import { useState } from 'react'
import { ClientForm } from '../client-form'
import type { Candidate } from '../../../types/discovery'
import type { Client, ClientCreate, ContactInfo } from '../../../types/client'

interface Props {
  candidates: Candidate[]
  onSaveClient: (data: ClientCreate) => Promise<void>
  onComplete: (summary: { created: number }) => void
}

function contactsFromCandidate(c: Candidate): ContactInfo[] {
  return c.top_senders.map((s) => ({ name: s.name, email: s.email }))
}

export function CandidateReviewWizard({ candidates, onSaveClient, onComplete }: Props) {
  const [index, setIndex] = useState(0)
  const [created, setCreated] = useState(0)
  const [saving, setSaving] = useState(false)

  if (candidates.length === 0) {
    // Guard — CandidateList prevents zero-select, but stay safe.
    onComplete({ created: 0 })
    return null
  }

  const isLast = index === candidates.length - 1
  const current = candidates[index]

  const advance = (didCreate: boolean) => {
    const newCreated = created + (didCreate ? 1 : 0)
    if (isLast) {
      onComplete({ created: newCreated })
      return
    }
    setCreated(newCreated)
    setIndex((i) => i + 1)
  }

  const handleSubmit = async (data: ClientCreate) => {
    if (saving) return
    setSaving(true)
    try {
      await onSaveClient(data)
      advance(true)
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => advance(false)

  // ClientForm is given an `initial` so its name field seeds from suggested_name,
  // and `initialContacts` so the contacts editor seeds from the candidate's top senders.
  const seededClient: Client = {
    id: '',
    slug: '',
    name: current.suggested_name,
    industry: null,
    size: null,
    contacts: contactsFromCandidate(current),
    notes: null,
    tags: [],
    context_profile: {},
    created_at: '',
    updated_at: '',
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-stone-500">
        Reviewing {index + 1} of {candidates.length} ·{' '}
        <span className="font-mono">{current.domain}</span>
      </div>
      <ClientForm
        key={current.domain}
        initial={seededClient}
        initialContacts={contactsFromCandidate(current)}
        onSubmit={handleSubmit}
        onCancel={handleSkip}
        saving={saving}
        submitLabel={isLast ? 'Save & Finish' : 'Save & Next'}
        cancelLabel="Skip this"
      />
    </div>
  )
}
