import { useState } from 'react'
import { useAuthStore } from '../../stores/auth-store'

interface Props {
  onSubmit: (data: Record<string, unknown>) => void
  saving: boolean
}

export function StepProfile({ onSubmit, saving }: Props) {
  const agency = useAuthStore((s) => s.agency)
  const [name, setName] = useState(agency?.name || '')
  const [primary, setPrimary] = useState(agency?.colours?.primary || '#1a1a1a')
  const [accent, setAccent] = useState(agency?.colours?.accent || '#ff6b35')
  const [headingFont, setHeadingFont] = useState('DM Serif Display')
  const [bodyFont, setBodyFont] = useState('DM Sans')

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-stone-700">Agency name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-stone-700">Primary colour</label>
          <div className="mt-1 flex items-center gap-2">
            <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} className="h-9 w-9 rounded border-0 cursor-pointer" />
            <input type="text" value={primary} onChange={(e) => setPrimary(e.target.value)} className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700">Accent colour</label>
          <div className="mt-1 flex items-center gap-2">
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} className="h-9 w-9 rounded border-0 cursor-pointer" />
            <input type="text" value={accent} onChange={(e) => setAccent(e.target.value)} className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-stone-700">Heading font</label>
          <input type="text" value={headingFont} onChange={(e) => setHeadingFont(e.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700">Body font</label>
          <input type="text" value={bodyFont} onChange={(e) => setBodyFont(e.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm" />
        </div>
      </div>

      <button
        onClick={() => onSubmit({ name, colours: { primary, accent }, fonts: { heading: headingFont, body: bodyFont } })}
        disabled={saving || !name}
        className="w-full rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Continue'}
      </button>
    </div>
  )
}
