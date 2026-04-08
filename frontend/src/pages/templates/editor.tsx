import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTemplate, useUpdateTemplate } from '../../api/templates'
import { CATEGORY_COLOURS } from '../../types/template'
import type { TemplateConfig } from '../../types/template'

const CONFIG_SECTIONS: { key: keyof TemplateConfig; label: string; description: string }[] = [
  { key: 'brief_intake', label: 'Brief Intake', description: 'Questions asked during brief gathering and auto-detect signals for template matching' },
  { key: 'research', label: 'Research', description: 'Search queries for client research and market benchmarking' },
  { key: 'cost_model', label: 'Cost Model', description: 'Default deliverables, multipliers, and pricing framing strategy' },
  { key: 'narrative', label: 'Narrative', description: 'Letter strategy, tone, scope detail level, and rationale depth' },
  { key: 'output', label: 'Output', description: 'Site theme, sections to include/skip, demo eligibility' },
]

function ConfigSection({ data, isEditable, onUpdate }: {
  data: Record<string, unknown>
  isEditable: boolean
  onUpdate: (key: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      {Object.entries(data).map(([field, value]) => (
        <div key={field} className="flex items-start gap-4">
          <label className="text-sm font-medium text-stone-500 w-48 flex-shrink-0 pt-1">
            {field.replace(/_/g, ' ')}
          </label>
          <div className="flex-1">
            {Array.isArray(value) ? (
              <div className="flex flex-wrap gap-1.5">
                {(value as string[]).map((item, i) => (
                  <span key={i} className="text-xs px-2 py-1 rounded-lg bg-stone-100 text-stone-600">
                    {String(item)}
                  </span>
                ))}
              </div>
            ) : typeof value === 'boolean' ? (
              <span className={`text-sm font-medium ${value ? 'text-green-600' : 'text-stone-400'}`}>
                {value ? 'Yes' : 'No'}
              </span>
            ) : isEditable ? (
              <input
                type="text"
                value={String(value || '')}
                onChange={(e) => onUpdate(field, e.target.value)}
                className="w-full rounded-lg border border-stone-300 px-3 py-1.5 text-sm"
              />
            ) : (
              <p className="text-sm text-stone-800">{String(value || '—')}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export function TemplateEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: template, isLoading } = useTemplate(id!)
  const updateTemplate = useUpdateTemplate()
  const [expanded, setExpanded] = useState<string | null>('narrative')

  if (isLoading) return <p className="text-sm text-stone-400">Loading...</p>
  if (!template) return <p className="text-sm text-stone-500">Template not found.</p>

  const isEditable = !template.is_system
  const config = template.config as TemplateConfig

  const handleConfigUpdate = (sectionKey: string, field: string, value: unknown) => {
    if (!isEditable) return
    const updatedConfig = { ...config }
    const section = { ...(updatedConfig[sectionKey as keyof TemplateConfig] as Record<string, unknown> || {}) }
    section[field] = value;
    (updatedConfig as Record<string, unknown>)[sectionKey] = section
    updateTemplate.mutate({ id: template.id, config: updatedConfig as Record<string, unknown> })
  }

  return (
    <div>
      <button onClick={() => navigate('/templates')} className="text-sm text-stone-500 hover:text-stone-700 mb-3">
        &larr; Back to templates
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${CATEGORY_COLOURS[template.category] || 'bg-stone-100 text-stone-600'}`}>
              {template.category}
            </span>
            {template.is_system && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-stone-100 text-stone-500">System (Read-only)</span>
            )}
          </div>
          <h1 className="text-2xl font-semibold text-stone-900">{template.name}</h1>
          {template.description && <p className="mt-1 text-sm text-stone-500">{template.description}</p>}
          <p className="mt-0.5 text-xs text-stone-400 font-mono">{template.template_key}</p>
        </div>
      </div>

      {/* Config sections */}
      <div className="mt-8 space-y-3">
        {CONFIG_SECTIONS.map((section) => {
          const sectionData = config[section.key]
          if (!sectionData || typeof sectionData !== 'object') return null
          const isOpen = expanded === section.key

          return (
            <div key={section.key} className="rounded-xl border border-stone-200 bg-white overflow-hidden">
              <button
                onClick={() => setExpanded(isOpen ? null : section.key)}
                className="w-full flex items-center justify-between px-5 py-4 hover:bg-stone-50 transition-colors text-left"
              >
                <div>
                  <h3 className="font-medium text-stone-900">{section.label}</h3>
                  <p className="text-xs text-stone-400 mt-0.5">{section.description}</p>
                </div>
                <svg className={`w-4 h-4 text-stone-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {isOpen && (
                <div className="border-t border-stone-100 px-5 py-4">
                  <ConfigSection
                    data={sectionData as Record<string, unknown>}
                    isEditable={isEditable}
                    onUpdate={(field, value) => handleConfigUpdate(section.key, field, value)}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {template.is_system && (
        <p className="mt-6 text-sm text-stone-400 text-center">
          This is a system template and cannot be edited. Clone it from the templates list to create your own version.
        </p>
      )}
    </div>
  )
}
