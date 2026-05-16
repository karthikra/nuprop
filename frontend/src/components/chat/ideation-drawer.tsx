import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../stores/chat-store'
import { useIdeationMessages, useSendIdeationMessage } from '../../api/proposals'
import type { ChatMessage } from '../../types/proposal'
import { TypingIndicator } from './message-bubble'

interface Props {
  open: boolean
  onClose: () => void
  proposalId: string
}

const SUGGESTIONS = [
  'What angle should we lead with?',
  'What would a retainer version of this look like?',
  'What objections might the client have?',
  'If we cut the budget by 30%, what would we drop?',
]

export function IdeationDrawer({ open, onClose, proposalId }: Props) {
  // Hydrate the store from the server on first open of this proposal.
  // Uses mergeIdeationMessages so a TanStack refetch is O(n) total, not O(n²).
  const { data: serverMsgs } = useIdeationMessages(proposalId)
  const addMessage = useChatStore((s) => s.addMessage)
  const mergeIdeationMessages = useChatStore((s) => s.mergeIdeationMessages)
  useEffect(() => {
    if (serverMsgs) {
      mergeIdeationMessages(serverMsgs.map((m) => ({ ...m, channel: 'ideation' })))
    }
  }, [serverMsgs, mergeIdeationMessages])

  const messages = useChatStore((s) => s.ideationMessages)
  const isIdeationTyping = useChatStore((s) => s.isIdeationTyping)
  const send = useSendIdeationMessage()

  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Close on Esc.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Auto-scroll to bottom when messages change.
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length])

  if (!open) return null

  const handleSend = async () => {
    const content = draft.trim()
    if (!content) return
    try {
      const created = await send.mutateAsync({ proposalId, content })
      setDraft('')
      for (const m of created) addMessage({ ...m, channel: 'ideation' })
    } catch (err) {
      console.error('ideation send failed', err)
      // Keep the draft so the user can retry — the worker-side errors arrive
      // as system messages via WS, but a network-layer POST failure leaves
      // no visible signal otherwise.
    }
  }

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-stone-900/30 transition-opacity"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Ideation"
        className="fixed right-0 top-0 bottom-0 z-50 w-full sm:w-[40vw] sm:max-w-[560px] bg-slate-50 border-l border-slate-200 flex flex-col"
      >
        <header className="border-b border-slate-200 px-5 py-4 flex items-start gap-3">
          <span aria-hidden className="text-lg">💡</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-900">Ideation</p>
            <p className="text-xs text-slate-600 leading-snug">
              Talking through this proposal with Claude. Read-only — nothing here modifies the main flow.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close ideation"
            className="text-slate-500 hover:text-slate-900"
          >
            ✕
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.length === 0 ? (
            <EmptyState
              onPick={(s) => {
                setDraft(s)
                inputRef.current?.focus()
              }}
            />
          ) : (
            messages.map((m) => <IdeationBubble key={m.id} message={m} />)
          )}
          {isIdeationTyping && (
            <div data-testid="ideation-typing">
              <TypingIndicator />
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3 flex gap-2">
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="Talk to Claude about this proposal…"
            rows={2}
            className="flex-1 resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!draft.trim() || send.isPending}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </aside>
    </>
  )
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-700 space-y-3">
      <p className="font-medium text-slate-900">💡 Think out loud about this proposal.</p>
      <p className="leading-relaxed">
        I can see everything the agency has put together so far — the brief, research,
        costing, narrative — but I won't change any of it. Use me to surface
        assumptions, try different angles, or stress-test the strategy.
      </p>
      <p className="text-xs uppercase tracking-wider text-slate-500">Try asking</p>
      <ul className="space-y-1">
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="text-left text-sm text-slate-700 hover:text-slate-900 hover:underline"
            >
              • {s}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function IdeationBubble({ message }: { message: ChatMessage }) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  if (extra.kind === 'error') {
    return (
      <div
        role="alert"
        data-error="ideation"
        className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
      >
        <span aria-hidden="true">⚠</span> {message.content}
      </div>
    )
  }
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-slate-900 text-white rounded-br-md'
            : 'bg-white border border-slate-200 text-slate-800 rounded-bl-md'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
