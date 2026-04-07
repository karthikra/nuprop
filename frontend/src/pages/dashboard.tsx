export function Dashboard() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-stone-900">Dashboard</h1>
      <p className="mt-1 text-sm text-stone-500">
        Welcome to NUPROP. Create your first proposal to get started.
      </p>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Active Proposals</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">0</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Win Rate</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">—</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Total Value</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">₹0</p>
        </div>
      </div>

      <div className="mt-8 rounded-xl border border-dashed border-stone-300 bg-white p-12 text-center">
        <p className="text-stone-500 text-sm">No proposals yet.</p>
        <a
          href="/proposals/new"
          className="mt-3 inline-block rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 transition-colors"
        >
          Create your first proposal
        </a>
      </div>
    </div>
  )
}
