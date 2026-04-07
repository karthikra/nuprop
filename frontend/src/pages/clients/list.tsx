import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useClients, useCreateClient, useDeleteClient } from '../../api/clients'
import { ClientForm } from '../../components/clients/client-form'
import type { ClientCreate } from '../../types/client'

export function ClientListPage() {
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const { data: clients, isLoading } = useClients(search || undefined)
  const createClient = useCreateClient()
  const deleteClient = useDeleteClient()

  const handleCreate = (data: ClientCreate) => {
    createClient.mutate(data, { onSuccess: () => setShowForm(false) })
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Clients</h1>
          <p className="mt-1 text-sm text-stone-500">{clients?.length ?? 0} clients</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
        >
          Add client
        </button>
      </div>

      {/* Search */}
      <div className="mt-6">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search clients..."
          className="w-full max-w-sm rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>

      {/* Create form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-stone-900 mb-4">New client</h2>
            <ClientForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              saving={createClient.isPending}
            />
          </div>
        </div>
      )}

      {/* Client list */}
      <div className="mt-6 space-y-2">
        {isLoading && <p className="text-sm text-stone-400">Loading...</p>}
        {clients?.length === 0 && !isLoading && (
          <div className="rounded-xl border border-dashed border-stone-300 bg-white p-8 text-center">
            <p className="text-sm text-stone-500">No clients yet.</p>
          </div>
        )}
        {clients?.map((client) => (
          <div
            key={client.id}
            className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 transition-colors"
          >
            <Link to={`/clients/${client.id}`} className="flex-1 min-w-0">
              <p className="font-medium text-stone-900 truncate">{client.name}</p>
              <div className="mt-0.5 flex items-center gap-3 text-xs text-stone-500">
                {client.industry && <span>{client.industry}</span>}
                {client.size && <span className="capitalize">{client.size}</span>}
                {client.tags.length > 0 && (
                  <span className="flex gap-1">
                    {client.tags.map((tag) => (
                      <span key={tag} className="rounded bg-stone-100 px-1.5 py-0.5">{tag}</span>
                    ))}
                  </span>
                )}
              </div>
            </Link>
            <button
              onClick={() => { if (confirm(`Delete ${client.name}?`)) deleteClient.mutate(client.id) }}
              className="ml-4 p-1.5 text-stone-400 hover:text-red-500 rounded"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
