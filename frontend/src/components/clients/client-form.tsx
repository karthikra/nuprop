import { useState } from 'react'
import type { Client, ClientCreate, ContactInfo } from '../../types/client'

interface Props {
  initial?: Client
  initialContacts?: ContactInfo[]
  onSubmit: (data: ClientCreate) => void
  onCancel: () => void
  saving: boolean
  submitLabel?: string
  cancelLabel?: string
}

const SIZE_OPTIONS = ['startup', 'sme', 'enterprise']

export function ClientForm({
  initial, initialContacts, onSubmit, onCancel, saving, submitLabel, cancelLabel,
}: Props) {
  const [name, setName] = useState(initial?.name || '')
  const [industry, setIndustry] = useState(initial?.industry || '')
  const [size, setSize] = useState(initial?.size || '')
  const [notes, setNotes] = useState(initial?.notes || '')
  const [tags, setTags] = useState(initial?.tags?.join(', ') || '')
  const [contacts, setContacts] = useState<ContactInfo[]>(
    initialContacts ?? initial?.contacts ?? [],
  )

  const updateContact = (idx: number, field: 'name' | 'email', value: string) => {
    setContacts((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)))
  }
  const addContact = () => setContacts((prev) => [...prev, { name: '', email: '' }])
  const removeContact = (idx: number) =>
    setContacts((prev) => prev.filter((_, i) => i !== idx))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanContacts = contacts
      .map((c) => ({ name: c.name.trim(), email: (c.email || '').trim() }))
      .filter((c) => c.name || c.email)
    onSubmit({
      name,
      industry: industry || undefined,
      size: size || undefined,
      notes: notes || undefined,
      tags: tags ? tags.split(',').map((t) => t.trim()).filter(Boolean) : [],
      contacts: cleanContacts.length ? cleanContacts : undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="client-name" className="block text-sm font-medium text-stone-700">Client name *</label>
        <input
          id="client-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-stone-700">Industry</label>
          <input
            type="text"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g. Telecom, Retail"
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700">Size</label>
          <select
            value={size}
            onChange={(e) => setSize(e.target.value)}
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          >
            <option value="">Select...</option>
            {SIZE_OPTIONS.map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-stone-700 mb-2">Contacts</label>
        <div className="space-y-2">
          {contacts.map((c, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Contact name"
                value={c.name}
                onChange={(e) => updateContact(idx, 'name', e.target.value)}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <input
                type="email"
                placeholder="Contact email"
                value={c.email || ''}
                onChange={(e) => updateContact(idx, 'email', e.target.value)}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <button
                type="button"
                onClick={() => removeContact(idx)}
                aria-label="Remove contact"
                className="text-stone-300 hover:text-red-500 text-sm px-1"
              >✕</button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={addContact}
          className="mt-2 text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900"
        >
          + Add contact
        </button>
      </div>
      <div>
        <label className="block text-sm font-medium text-stone-700">Tags</label>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="repeat, tech, priority (comma-separated)"
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-stone-700">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Internal notes about this client..."
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>
      <div className="flex justify-end gap-3 pt-2">
        <button type="button" onClick={onCancel} className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900">
          {cancelLabel ?? 'Cancel'}
        </button>
        <button
          type="submit"
          disabled={saving || !name}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {saving ? 'Saving...' : (submitLabel ?? (initial ? 'Update' : 'Create'))}
        </button>
      </div>
    </form>
  )
}
