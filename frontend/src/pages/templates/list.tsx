import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTemplates, useCloneTemplate, useDeleteTemplate } from '../../api/templates'
import { CATEGORY_COLOURS } from '../../types/template'

export function TemplateListPage() {
  const { data: templates, isLoading } = useTemplates()
  const cloneTemplate = useCloneTemplate()
  const deleteTemplate = useDeleteTemplate()
  const [cloning, setCloning] = useState<string | null>(null)
  const [cloneName, setCloneName] = useState('')

  const systemTemplates = templates?.filter((t) => t.is_system) || []
  const customTemplates = templates?.filter((t) => !t.is_system) || []

  const handleClone = (id: string) => {
    if (!cloneName.trim()) return
    const key = cloneName.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '')
    cloneTemplate.mutate(
      { id, new_key: `custom-${key}`, new_name: cloneName.trim() },
      { onSuccess: () => { setCloning(null); setCloneName('') } },
    )
  }

  if (isLoading) return <p className="text-sm text-stone-400">Loading templates...</p>

  return (
    <div>
      <h1 className="text-2xl font-semibold text-stone-900">Strategy Templates</h1>
      <p className="mt-1 text-sm text-stone-500">
        Templates shape how the AI researches, prices, and writes for each proposal type.
      </p>

      {/* Custom templates */}
      {customTemplates.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-3">Your Templates</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {customTemplates.map((t) => (
              <div key={t.id} className="rounded-xl border border-stone-200 bg-white p-5 hover:border-stone-300 transition-colors">
                <div className="flex items-start justify-between">
                  <Link to={`/templates/${t.id}`} className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${CATEGORY_COLOURS[t.category] || 'bg-stone-100 text-stone-600'}`}>
                        {t.category}
                      </span>
                    </div>
                    <h3 className="font-medium text-stone-900">{t.name}</h3>
                    {t.description && <p className="text-sm text-stone-500 mt-1 line-clamp-2">{t.description}</p>}
                  </Link>
                  <button
                    onClick={() => { if (confirm(`Delete "${t.name}"?`)) deleteTemplate.mutate(t.id) }}
                    className="p-1 text-stone-300 hover:text-red-500 ml-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* System templates */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-3">
          System Templates {systemTemplates.length > 0 && `(${systemTemplates.length})`}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {systemTemplates.map((t) => (
            <div key={t.id} className="rounded-xl border border-stone-200 bg-white p-5">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${CATEGORY_COLOURS[t.category] || 'bg-stone-100 text-stone-600'}`}>
                  {t.category}
                </span>
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-stone-100 text-stone-500">System</span>
              </div>
              <Link to={`/templates/${t.id}`}>
                <h3 className="font-medium text-stone-900 hover:underline">{t.name}</h3>
              </Link>
              {t.description && <p className="text-sm text-stone-500 mt-1 line-clamp-2">{t.description}</p>}

              {/* Config summary */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {t.config?.narrative?.letter_strategy && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-50 text-stone-500">
                    Letter: {t.config.narrative.letter_strategy}
                  </span>
                )}
                {t.config?.cost_model?.pricing_framing && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-50 text-stone-500">
                    Pricing: {t.config.cost_model.pricing_framing}
                  </span>
                )}
                {t.config?.output?.site_theme && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-50 text-stone-500">
                    Theme: {t.config.output.site_theme}
                  </span>
                )}
              </div>

              {/* Clone button */}
              <div className="mt-3">
                {cloning === t.id ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={cloneName}
                      onChange={(e) => setCloneName(e.target.value)}
                      placeholder="New template name"
                      className="flex-1 rounded-lg border border-stone-300 px-2 py-1 text-sm"
                      autoFocus
                      onKeyDown={(e) => { if (e.key === 'Enter') handleClone(t.id); if (e.key === 'Escape') setCloning(null) }}
                    />
                    <button
                      onClick={() => handleClone(t.id)}
                      disabled={!cloneName.trim() || cloneTemplate.isPending}
                      className="rounded-lg bg-stone-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                    >
                      Clone
                    </button>
                    <button onClick={() => setCloning(null)} className="text-xs text-stone-400">Cancel</button>
                  </div>
                ) : (
                  <button
                    onClick={() => { setCloning(t.id); setCloneName(`${t.name} (Custom)`) }}
                    className="text-xs text-stone-500 hover:text-stone-900"
                  >
                    Clone to customize →
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
