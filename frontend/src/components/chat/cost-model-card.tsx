import { useState } from 'react'
import { api } from '../../api/client'
import type { ChatMessage } from '../../types/proposal'

interface CostLineItem {
  deliverable: string
  package_id: string | null
  package_name: string
  match_quality: string
  quantity: number
  unit_cost: number
  total: number
  notes: string
}

interface CostModelData {
  line_items: CostLineItem[]
  subtotal: number
  discount_percent: number
  discount_amount: number
  total: number
  gst_rate: number
  gst_amount: number
  grand_total: number
  currency: string
  multipliers_applied: string[]
}

interface Props {
  message: ChatMessage
  proposalId: string
}

function formatCurrency(amount: number): string {
  if (amount >= 10000000) return `₹${(amount / 10000000).toFixed(2)} Cr`
  if (amount >= 100000) return `₹${(amount / 100000).toFixed(1)} L`
  return `₹${amount.toLocaleString('en-IN')}`
}

const MATCH_BADGES: Record<string, string> = {
  exact: 'bg-green-100 text-green-700',
  close: 'bg-amber-100 text-amber-700',
  hourly: 'bg-stone-100 text-stone-600',
}

export function CostModelCard({ message, proposalId }: Props) {
  const extra = message.extra_data as Record<string, unknown>
  const initialModel = extra?.cost_model as CostModelData | undefined
  const [model, setModel] = useState<CostModelData | null>(initialModel || null)
  const [editingCell, setEditingCell] = useState<{ index: number; field: string } | null>(null)
  const [editValue, setEditValue] = useState('')
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)

  if (!model) return null

  const handleCellClick = (index: number, field: string, currentValue: number) => {
    setEditingCell({ index, field })
    setEditValue(String(currentValue))
  }

  const handleCellSave = async () => {
    if (!editingCell) return
    const value = parseInt(editValue, 10)
    if (isNaN(value) || value < 0) {
      setEditingCell(null)
      return
    }

    try {
      const { data } = await api.patch(`/chat/${proposalId}/cost-model`, {
        index: editingCell.index,
        field: editingCell.field,
        value,
      })
      setModel(data as CostModelData)
    } catch (err) {
      console.error('Failed to update cost model:', err)
    }
    setEditingCell(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCellSave()
    if (e.key === 'Escape') setEditingCell(null)
  }

  const handleApprove = async () => {
    setApproving(true)
    try {
      await api.post(`/chat/${proposalId}/approve/cost_model`, { data: {} })
      setApproved(true)
    } catch (err) {
      console.error('Approval failed:', err)
    }
    setApproving(false)
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8V7m0 1v8m0 0v1" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-emerald-900">Cost Model — Review & Approve</span>
          <span className="text-xs text-emerald-600 ml-auto">Click any price or quantity to edit</span>
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-emerald-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-emerald-100/50 text-left text-xs font-medium text-emerald-800 uppercase tracking-wider">
                <th className="px-3 py-2">Deliverable</th>
                <th className="px-3 py-2">Package</th>
                <th className="px-3 py-2 text-center">Qty</th>
                <th className="px-3 py-2 text-right">Unit Cost</th>
                <th className="px-3 py-2 text-right">Total</th>
                <th className="px-3 py-2 text-center">Match</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-emerald-100">
              {model.line_items.map((item, i) => (
                <tr key={i} className="hover:bg-emerald-50/50">
                  <td className="px-3 py-2 font-medium text-stone-900 max-w-[200px] truncate">
                    {item.deliverable}
                  </td>
                  <td className="px-3 py-2 text-stone-500 max-w-[180px] truncate text-xs">
                    {item.package_name}
                  </td>
                  <td
                    className="px-3 py-2 text-center cursor-pointer hover:bg-emerald-100 rounded"
                    onClick={() => handleCellClick(i, 'quantity', item.quantity)}
                  >
                    {editingCell?.index === i && editingCell?.field === 'quantity' ? (
                      <input
                        type="number"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={handleCellSave}
                        onKeyDown={handleKeyDown}
                        autoFocus
                        className="w-16 text-center rounded border border-emerald-300 px-1 py-0.5 text-sm"
                      />
                    ) : (
                      item.quantity
                    )}
                  </td>
                  <td
                    className="px-3 py-2 text-right cursor-pointer hover:bg-emerald-100 rounded"
                    onClick={() => handleCellClick(i, 'unit_cost', item.unit_cost)}
                  >
                    {editingCell?.index === i && editingCell?.field === 'unit_cost' ? (
                      <input
                        type="number"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={handleCellSave}
                        onKeyDown={handleKeyDown}
                        autoFocus
                        className="w-24 text-right rounded border border-emerald-300 px-1 py-0.5 text-sm"
                      />
                    ) : (
                      formatCurrency(item.unit_cost)
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-medium text-stone-900">
                    {formatCurrency(item.total)}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${MATCH_BADGES[item.match_quality] || MATCH_BADGES.hourly}`}>
                      {item.match_quality}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Summary */}
        <div className="mt-4 space-y-1 text-sm text-right">
          <p className="text-stone-600">Subtotal: <span className="font-medium text-stone-900">{formatCurrency(model.subtotal)}</span></p>
          {model.discount_percent > 0 && (
            <p className="text-green-700">Discount ({model.discount_percent}%): <span className="font-medium">−{formatCurrency(model.discount_amount)}</span></p>
          )}
          <p className="text-stone-600">Total (excl. GST): <span className="font-semibold text-stone-900">{formatCurrency(model.total)}</span></p>
          <p className="text-stone-500">GST (18%): {formatCurrency(model.gst_amount)}</p>
          <p className="text-lg font-bold text-stone-900">Grand Total: {formatCurrency(model.grand_total)}</p>
        </div>

        {model.multipliers_applied.length > 0 && (
          <p className="mt-2 text-xs text-stone-500">
            Multipliers: {model.multipliers_applied.join(', ')}
          </p>
        )}

        {/* Approve / Adjust */}
        {!approved ? (
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleApprove}
              disabled={approving}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {approving ? 'Approving...' : 'Approve Cost Model'}
            </button>
            <button
              disabled={approving}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
            >
              Adjust
            </button>
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Approved — advancing to narrative generation
          </div>
        )}
      </div>
    </div>
  )
}
