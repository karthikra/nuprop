import { useState } from 'react'
import { useDiscoverClients } from '../../../api/discovery'
import { useCreateClient } from '../../../api/clients'
import { formatApiError } from '../../../api/client'
import { LookbackPicker } from './lookback-picker'
import { CandidateList } from './candidate-list'
import { CandidateReviewWizard } from './candidate-review-wizard'
import type { Candidate, DiscoveryResponse, LookbackDays } from '../../../types/discovery'
import type { ClientCreate } from '../../../types/client'

interface Props {
  open: boolean
  onClose: () => void
  onComplete: (summary: { created: number }) => void
}

type Phase =
  | { kind: 'lookback' }
  | { kind: 'scanning' }
  | { kind: 'list'; response: DiscoveryResponse }
  | { kind: 'wizard'; selected: Candidate[] }
  | { kind: 'done'; created: number }
  | { kind: 'error'; message: string }

export function ClientDiscoveryFlow({ open, onClose, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'lookback' })
  const discover = useDiscoverClients()
  const createClient = useCreateClient()

  if (!open) return null

  const handlePickLookback = async (days: LookbackDays) => {
    setPhase({ kind: 'scanning' })
    try {
      const response = await discover.mutateAsync(days)
      setPhase({ kind: 'list', response })
    } catch (err: unknown) {
      const message = formatApiError(err, 'Could not scan your inbox right now.')
      setPhase({ kind: 'error', message })
    }
  }

  const handleReview = (selected: Candidate[]) => {
    setPhase({ kind: 'wizard', selected })
  }

  const handleSkipAll = () => {
    setPhase({ kind: 'done', created: 0 })
  }

  const handleSaveClient = async (data: ClientCreate) => {
    await createClient.mutateAsync(data)
  }

  const handleWizardComplete = ({ created }: { created: number }) => {
    setPhase({ kind: 'done', created })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-lg">
        {phase.kind === 'lookback' && (
          <LookbackPicker onPick={handlePickLookback} onCancel={onClose} />
        )}
        {phase.kind === 'scanning' && (
          <div className="py-12 text-center">
            <p className="text-sm text-stone-500">Scanning your inbox…</p>
          </div>
        )}
        {phase.kind === 'list' && (
          <CandidateList
            response={phase.response}
            onReview={handleReview}
            onSkipAll={handleSkipAll}
          />
        )}
        {phase.kind === 'wizard' && (
          <CandidateReviewWizard
            candidates={phase.selected}
            onSaveClient={handleSaveClient}
            onComplete={handleWizardComplete}
          />
        )}
        {phase.kind === 'done' && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-stone-900">
              {phase.created > 0
                ? `Created ${phase.created} ${phase.created === 1 ? 'client' : 'clients'}`
                : 'No clients created'}
            </h2>
            <p className="text-sm text-stone-600">
              {phase.created > 0
                ? 'They now appear in your client list.'
                : 'Nothing was added. You can run discovery again any time.'}
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => onComplete({ created: phase.created })}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
              >
                Done
              </button>
            </div>
          </div>
        )}
        {phase.kind === 'error' && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-stone-900">Couldn't scan your inbox</h2>
            <p className="text-sm text-stone-600">{phase.message}</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
              >
                Close
              </button>
              <button
                onClick={() => setPhase({ kind: 'lookback' })}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
              >
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
