import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useProposal, useChatMessages } from '../../api/proposals'
import { useClient } from '../../api/clients'
import { useTemplate } from '../../api/templates'
import { useChatStore } from '../../stores/chat-store'
import { useProposalWebSocket } from '../../hooks/use-websocket'
import { Nav } from '../../components/layout/nav'
import { PipelineSidebar } from '../../components/chat/pipeline-sidebar'
import { ChatContainer } from '../../components/chat/chat-container'
import { PreferencePanel } from '../../components/chat/preference-panel'
import { IdeateButton } from '../../components/chat/ideate-button'
import { IdeationDrawer } from '../../components/chat/ideation-drawer'

export function BuilderPage() {
  const { id } = useParams<{ id: string }>()
  const { data: proposal, isLoading: loadingProposal } = useProposal(id!)
  const { data: initialMessages } = useChatMessages(id!)
  const { data: client } = useClient(proposal?.client_id || '')
  const { data: template } = useTemplate(proposal?.template_id || '')

  const setMessages = useChatStore((s) => s.setMessages)
  const setPipelinePhase = useChatStore((s) => s.setPipelinePhase)
  const reset = useChatStore((s) => s.reset)

  const [ideateOpen, setIdeateOpen] = useState(false)

  useEffect(() => {
    if (initialMessages) setMessages(initialMessages)
  }, [initialMessages, setMessages])

  useEffect(() => {
    if (proposal) setPipelinePhase(proposal.pipeline_state.current_phase)
  }, [proposal, setPipelinePhase])

  useProposalWebSocket(id)

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
      {/* top-14 matches Nav's h-14; z-50 keeps the button visible above the drawer's overlay */}
      <div className="fixed top-14 right-6 z-50">
        <IdeateButton open={ideateOpen} onToggle={setIdeateOpen} />
      </div>
      <div className="flex pt-14 h-screen">
        <PipelineSidebar proposal={proposal} clientName={client?.name} />
        <main className="flex-1 flex flex-col min-w-0">
          <ChatContainer
            proposalId={id!}
            clientId={proposal.client_id}
            clientName={client?.name}
            clientHasContext={!!client?.context_profile && Object.keys(client.context_profile).length > 0}
            rateCardGaps={proposal.rate_card_gaps}
          />
        </main>
        <PreferencePanel proposal={proposal} templateConfig={template?.config} />
      </div>
      <IdeationDrawer open={ideateOpen} onClose={() => setIdeateOpen(false)} proposalId={id!} />
    </div>
  )
}
