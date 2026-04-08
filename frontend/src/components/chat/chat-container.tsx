import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../stores/chat-store'
import { useSendMessage } from '../../api/proposals'
import { MessageBubble, TypingIndicator, ProgressTracker } from './message-bubble'
import { ChatInput } from './chat-input'
import { ContextCheck } from './context-check'

interface Props {
  proposalId: string
  clientId?: string
  clientName?: string
  clientHasContext?: boolean
}

export function ChatContainer({ proposalId, clientId, clientName, clientHasContext }: Props) {
  const messages = useChatStore((s) => s.messages)
  const isSending = useChatStore((s) => s.isSending)
  const isTyping = useChatStore((s) => s.isTyping)
  const setSending = useChatStore((s) => s.setSending)
  const isConnected = useChatStore((s) => s.isConnected)
  const progress = useChatStore((s) => s.progress)
  const sendMessage = useSendMessage()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [contextDone, setContextDone] = useState(!!clientHasContext)

  const handleSend = async (content: string) => {
    setSending(true)
    try {
      await sendMessage.mutateAsync({ proposalId, content })
    } finally {
      setSending(false)
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isTyping])

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Context check — shown for new proposals */}
        {messages.length === 0 && clientId && clientName && (
          <ContextCheck
            clientId={clientId}
            clientName={clientName}
            hasContext={contextDone}
            onComplete={() => setContextDone(true)}
          />
        )}
        {messages.length === 0 && contextDone && !isTyping && (
          <div className="flex items-center justify-center flex-1">
            <div className="text-center">
              <p className="text-lg font-medium text-stone-900">Start your proposal</p>
              <p className="mt-1 text-sm text-stone-500 max-w-sm">
                Tell me about the client and what they need. I'll guide you through research, pricing, and narrative.
              </p>
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} proposalId={proposalId} />
        ))}
        {progress.length > 0 && <ProgressTracker items={progress} />}
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-stone-200 bg-white px-6 py-4">
        <ChatInput onSend={handleSend} disabled={isSending || isTyping} />
        <div className="mt-2 flex items-center gap-2 text-[10px] text-stone-400">
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-400' : 'bg-stone-300'}`} />
          {isConnected ? 'Connected' : 'Connecting...'}
          {isTyping && <span className="ml-2 text-stone-500">AI is thinking...</span>}
        </div>
      </div>
    </div>
  )
}
