import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useClients } from '../../api/clients'
import { useCreateProposal } from '../../api/proposals'

export function NewProposalPage() {
  const navigate = useNavigate()
  const { data: clients, isLoading: loadingClients } = useClients()
  const createProposal = useCreateProposal()
  const [clientId, setClientId] = useState('')
  const [projectName, setProjectName] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!clientId || !projectName) return
    setError('')
    try {
      const proposal = await createProposal.mutateAsync({
        client_id: clientId,
        project_name: projectName,
      })
      navigate(`/proposals/${proposal.id}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create proposal')
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <h1 className="text-2xl font-semibold text-stone-900">New Proposal</h1>
      <p className="mt-1 text-sm text-stone-500">Select a client and name your project.</p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-stone-700">Client</label>
          <select
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            required
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          >
            <option value="">Select a client...</option>
            {loadingClients && <option disabled>Loading...</option>}
            {clients?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}{c.industry ? ` — ${c.industry}` : ''}
              </option>
            ))}
          </select>
          {clients?.length === 0 && !loadingClients && (
            <p className="mt-1 text-xs text-stone-400">
              No clients yet.{' '}
              <a href="/clients" className="text-stone-900 underline">Create one first</a>.
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-stone-700">Project name</label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="e.g. 25th Anniversary Campaign"
            required
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
          />
        </div>

        <button
          type="submit"
          disabled={createProposal.isPending || !clientId || !projectName}
          className="w-full rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {createProposal.isPending ? 'Creating...' : 'Start Proposal'}
        </button>
      </form>
    </div>
  )
}
