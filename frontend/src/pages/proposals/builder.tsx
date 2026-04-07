import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useProposal, useChatMessages } from '../../api/proposals'
import { useClient } from '../../api/clients'
import { useChatStore } from '../../stores/chat-store'
import { useProposalWebSocket } from '../../hooks/use-websocket'
import { Nav } from '../../components/layout/nav'
import { PipelineSidebar } from '../../components/chat/pipeline-sidebar'
import { ChatContainer } from '../../components/chat/chat-container'

export function BuilderPage() {
  const { id } = useParams<{ id: string }>()
  const { data: proposal, isLoading: loadingProposal } = useProposal(id!)
  const { data: initialMessages } = useChatMessages(id!)
  const { data: client } = useClient(proposal?.client_id || '')

  const setMessages = useChatStore((s) => s.setMessages)
  const setPipelinePhase = useChatStore((s) => s.setPipelinePhase)
  const reset = useChatStore((s) => s.reset)

  // Load initial messages into store
  useEffect(() => {
    if (initialMessages) setMessages(initialMessages)
  }, [initialMessages, setMessages])

  // Set pipeline phase from proposal
  useEffect(() => {
    if (proposal) setPipelinePhase(proposal.pipeline_state.current_phase)
  }, [proposal, setPipelinePhase])

  // Connect WebSocket
  useProposalWebSocket(id)

  // Cleanup on unmount
  useEffect(() => () => reset(), [reset])

  if (loadingProposal) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="animate-spin h-6 w-6 border-2 border-stone-900 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!proposal) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <p className="text-sm text-stone-500">Proposal not found.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <Nav />
      <div className="flex pt-14 h-screen">
        <PipelineSidebar proposal={proposal} clientName={client?.name} />
        <main className="flex-1 flex flex-col min-w-0">
          <ChatContainer proposalId={id!} />
        </main>
      </div>
    </div>
  )
}
