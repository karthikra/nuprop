import { useEffect, useRef } from 'react'
import { useChatStore } from '../stores/chat-store'
import type { WSMessage } from '../types/proposal'

export function useProposalWebSocket(proposalId: string | undefined) {
  const addMessage = useChatStore((s) => s.addMessage)
  const setPipelinePhase = useChatStore((s) => s.setPipelinePhase)
  const setConnected = useChatStore((s) => s.setConnected)
  const setTyping = useChatStore((s) => s.setTyping)
  const updateProgress = useChatStore((s) => s.updateProgress)
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
            setTyping(false)
          } else if (data.type === 'phase_change' && data.phase) {
            setPipelinePhase(data.phase)
          } else if (data.type === 'typing') {
            setTyping(!!data.typing)
          } else if (data.type === 'progress' && data.agent) {
            updateProgress({
              agent: data.agent,
              status: (data.status as 'searching' | 'complete' | 'error') || 'searching',
              detail: data.detail || '',
            })
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
  }, [proposalId, addMessage, setPipelinePhase, setConnected, setTyping, updateProgress])
}
