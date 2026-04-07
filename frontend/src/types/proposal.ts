export interface Proposal {
  id: string
  agency_id: string
  client_id: string
  project_name: string
  status: string
  brief: Record<string, unknown>
  template_id: string | null
  preferences: Record<string, unknown>
  pipeline_state: PipelineState
  created_at: string
  updated_at: string
}

export interface ProposalListItem {
  id: string
  client_id: string
  client_name: string
  project_name: string
  status: string
  pipeline_state: PipelineState
  created_at: string
  updated_at: string
}

export interface ProposalCreate {
  client_id: string
  project_name: string
}

export interface PipelineState {
  current_phase: string
  phases_completed: string[]
  context: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  proposal_id: string
  role: 'user' | 'assistant' | 'system'
  message_type: string
  content: string
  extra_data: Record<string, unknown>
  phase: string | null
  created_at: string
}

export interface WSMessage {
  type: 'new_message' | 'phase_change' | 'typing' | 'progress' | 'pong' | 'error'
  message?: ChatMessage
  phase?: string
  typing?: boolean
  agent?: string
  status?: string
  detail?: string
  error?: string
}

export interface ProgressItem {
  agent: string
  status: 'searching' | 'complete' | 'error'
  detail: string
}

export const PIPELINE_PHASES = [
  { key: 'brief', label: 'Brief' },
  { key: 'template_confirm', label: 'Template' },
  { key: 'research', label: 'Research' },
  { key: 'cost_model_review', label: 'Cost Model' },
  { key: 'narrative_review', label: 'Narrative' },
  { key: 'output_generation', label: 'Output' },
  { key: 'complete', label: 'Complete' },
] as const

export const STATUS_COLOURS: Record<string, string> = {
  draft: 'bg-stone-100 text-stone-600',
  generating: 'bg-amber-100 text-amber-700',
  review: 'bg-blue-100 text-blue-700',
  sent: 'bg-green-100 text-green-700',
  viewed: 'bg-emerald-100 text-emerald-700',
  won: 'bg-emerald-200 text-emerald-800',
  lost: 'bg-red-100 text-red-700',
  expired: 'bg-stone-200 text-stone-500',
}
