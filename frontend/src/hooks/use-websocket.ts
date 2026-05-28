import { useEffect, useRef } from 'react'
import { useChatStore } from '../stores/chat-store'
import type { WSMessage } from '../types/proposal'

export function useProposalWebSocket(proposalId: string | undefined) {
  const addMessage = useChatStore((s) => s.addMessage)
  const updateMessage = useChatStore((s) => s.updateMessage)
  const setPipelinePhase = useChatStore((s) => s.setPipelinePhase)
  const setConnected = useChatStore((s) => s.setConnected)
  const setTyping = useChatStore((s) => s.setTyping)
  const setIdeationTyping = useChatStore((s) => s.setIdeationTyping)
  const updateProgress = useChatStore((s) => s.updateProgress)
  const setJobStatus = useChatStore((s) => s.setJobStatus)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (!proposalId) return

    function connect() {
      const token = localStorage.getItem('nuprop_token')
      if (!token) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const ws = new WebSocket(
        `${protocol}//${host}/api/v1/chat/${proposalId}/ws?token=${token}`
      )

      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        clearTimeout(reconnectTimeout.current)
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimeout.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onmessage = (event) => {
        try {
          const data: WSMessage = JSON.parse(event.data)
          if (data.type === 'new_message' && data.message) {
            addMessage(data.message)
            // Clear the typing indicator for the channel the message arrived on.
            if (data.message.channel === 'ideation') {
              setIdeationTyping(false)
            } else {
              setTyping(false)
            }
          } else if (data.type === 'message_updated' && data.message) {
            updateMessage(data.message)
          } else if (data.type === 'phase_change' && data.phase) {
            setPipelinePhase(data.phase)
          } else if (data.type === 'typing') {
            // Route typing events by channel — default to main when omitted so
            // existing main-pipeline emits (which don't carry a channel) keep
            // working unchanged.
            if (data.channel === 'ideation') {
              setIdeationTyping(!!data.typing)
            } else {
              setTyping(!!data.typing)
            }
          } else if (data.type === 'progress' && data.agent) {
            updateProgress({
              agent: data.agent,
              status: (data.status as 'searching' | 'complete' | 'error') || 'searching',
              detail: data.detail || '',
            })
          } else if (data.type === 'job_status' && data.phase && data.state) {
            setJobStatus({
              phase: data.phase,
              state: data.state,
              error: data.error ?? null,
              updated_at: data.updated_at,
            })
          } else if (data.type === 'pipeline_error') {
            // Observability only — the user-facing error message arrives as a separate
            // new_message event with role=system + extra_data.kind=error.
            console.warn('pipeline_error:', data)
          }
        } catch {
          // ignore malformed messages
        }
      }
    }

    connect()

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      clearTimeout(reconnectTimeout.current)
      clearInterval(pingInterval)
      if (wsRef.current) {
        wsRef.current.onclose = null // prevent reconnect on intentional close
        wsRef.current.close()
      }
      setConnected(false)
    }
  }, [proposalId, addMessage, updateMessage, setPipelinePhase, setConnected, setTyping, setIdeationTyping, updateProgress, setJobStatus])
}
