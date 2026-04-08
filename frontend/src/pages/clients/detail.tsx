import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useClient, useUpdateClient, useDeleteClient } from '../../api/clients'
import { ClientForm } from '../../components/clients/client-form'
import type { ClientCreate } from '../../types/client'

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: client, isLoading } = useClient(id!)
  const updateClient = useUpdateClient()
  const deleteClient = useDeleteClient()
  const [editing, setEditing] = useState(false)

  if (isLoading) return <p className="text-sm text-stone-400">Loading...</p>
  if (!client) return <p className="text-sm text-stone-500">Client not found.</p>

  const handleUpdate = (data: ClientCreate) => {
    updateClient.mutate({ id: client.id, ...data }, { onSuccess: () => setEditing(false) })
  }

  const handleDelete = () => {
    if (confirm(`Delete ${client.name}? This cannot be undone.`)) {
      deleteClient.mutate(client.id, { onSuccess: () => navigate('/clients') })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate('/clients')} className="text-sm text-stone-500 hover:text-stone-700 mb-2">
            &larr; Back to clients
          </button>
          <h1 className="text-2xl font-semibold text-stone-900">{client.name}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-stone-500">
            {client.industry && <span>{client.industry}</span>}
            {client.size && <span className="capitalize">{client.size}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setEditing(!editing)}
            className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            {editing ? 'Cancel' : 'Edit'}
          </button>
          <button
            onClick={handleDelete}
            className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            Delete
          </button>
        </div>
      </div>

      {editing ? (
        <div className="mt-6 max-w-md">
          <ClientForm
            initial={client}
            onSubmit={handleUpdate}
            onCancel={() => setEditing(false)}
            saving={updateClient.isPending}
          />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Details card */}
          <div className="rounded-xl border border-stone-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide">Details</h3>
            <dl className="mt-3 space-y-3 text-sm">
              {client.tags.length > 0 && (
                <div>
                  <dt className="text-stone-500">Tags</dt>
                  <dd className="mt-0.5 flex gap-1">
                    {client.tags.map((tag) => (
                      <span key={tag} className="rounded bg-stone-100 px-2 py-0.5 text-xs">{tag}</span>
                    ))}
                  </dd>
                </div>
              )}
              {client.notes && (
                <div>
                  <dt className="text-stone-500">Notes</dt>
                  <dd className="mt-0.5 text-stone-900 whitespace-pre-wrap">{client.notes}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Contacts card */}
          <div className="rounded-xl border border-stone-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide">Contacts</h3>
            {client.contacts.length === 0 ? (
              <p className="mt-3 text-sm text-stone-400">No contacts added.</p>
            ) : (
              <div className="mt-3 space-y-3">
                {client.contacts.map((c, i) => (
                  <div key={i} className="text-sm">
                    <p className="font-medium text-stone-900">{c.name}</p>
                    {c.role && <p className="text-stone-500">{c.role}</p>}
                    {c.email && <p className="text-stone-500">{c.email}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Context Profile card */}
          <ContextProfileCard profile={client.context_profile} />

          {/* Proposals card (placeholder) */}
          <div className="rounded-xl border border-dashed border-stone-300 bg-white p-5 md:col-span-2">
            <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide">Proposals</h3>
            <p className="mt-3 text-sm text-stone-400">No proposals for this client yet.</p>
          </div>
        </div>
      )}
    </div>
  )
}

function ContextProfileCard({ profile }: { profile: Record<string, unknown> }) {
  if (!profile || Object.keys(profile).length === 0) return null

  const rel = profile.relationship as Record<string, unknown> | undefined
  const pricing = profile.pricing_intelligence as Record<string, unknown> | undefined
  const pastWork = Array.isArray(profile.past_work) ? profile.past_work as Array<Record<string, unknown>> : []
  const risks = Array.isArray(profile.risks) ? profile.risks as Array<Record<string, unknown>> : []

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide">Client Context</h3>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        {rel?.status != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Relationship</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(rel.status)}</dd>
          </div>
        ) : null}
        {pricing?.price_sensitivity != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Price Sensitivity</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(pricing.price_sensitivity)}</dd>
          </div>
        ) : null}
        {pastWork.length > 0 && (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Past Work</dt>
            <dd className="mt-1 space-y-1">
              {pastWork.map((w, i) => (
                <p key={i} className="text-stone-700">
                  <span className="font-medium">{String(w.project || '')}</span>
                  {w.value != null ? <span className="text-stone-500"> — ₹{Number(w.value).toLocaleString()}</span> : null}
                  {w.status != null ? <span className="text-stone-400"> ({String(w.status)})</span> : null}
                </p>
              ))}
            </dd>
          </div>
        )}
        {risks.length > 0 ? (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Risks</dt>
            <dd className="mt-1 space-y-1">
              {risks.map((r, i) => (
                <p key={i} className="text-stone-700 text-xs">⚠ {String(r.signal || '')}</p>
              ))}
            </dd>
          </div>
        ) : null}
      </div>
    </div>
  )
}
