interface ContextProfileCardProps {
  profile: Record<string, unknown>
}

export function ContextProfileCard({ profile }: ContextProfileCardProps) {
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
