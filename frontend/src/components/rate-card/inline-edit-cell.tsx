import { useState, useRef, useEffect } from 'react'

interface Props {
  value: number | string
  onSave: (newValue: number | string) => void
  format?: 'currency' | 'number' | 'percent' | 'text'
  className?: string
}

function formatDisplay(value: number | string, format: string): string {
  if (typeof value === 'string') return value
  if (format === 'currency') return `₹${value.toLocaleString('en-IN')}`
  if (format === 'percent') return `${(value * 100).toFixed(0)}%`
  return String(value)
}

export function InlineEditCell({ value, onSave, format = 'number', className = '' }: Props) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(String(format === 'percent' ? (value as number) * 100 : value))
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const handleSave = () => {
    setEditing(false)
    const trimmed = editValue.trim()
    if (!trimmed) return

    if (format === 'text') {
      if (trimmed !== value) onSave(trimmed)
      return
    }

    let num = parseFloat(trimmed)
    if (isNaN(num)) return
    if (format === 'percent') num = num / 100
    if (format === 'currency' || format === 'number') num = Math.round(num)
    if (num !== value) onSave(num)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') setEditing(false)
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        type={format === 'text' ? 'text' : 'number'}
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className={`w-full rounded border border-stone-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900 ${className}`}
      />
    )
  }

  return (
    <span
      onClick={() => {
        setEditValue(String(format === 'percent' ? (value as number) * 100 : value))
        setEditing(true)
      }}
      className={`cursor-pointer hover:bg-stone-100 rounded px-2 py-1 -mx-2 -my-1 transition-colors group ${className}`}
    >
      {formatDisplay(value, format)}
      <svg className="w-3 h-3 inline-block ml-1 text-stone-300 group-hover:text-stone-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    </span>
  )
}
