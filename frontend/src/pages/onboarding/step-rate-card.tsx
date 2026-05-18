import { RateCardWizard, type RateCardPayload } from '../../components/rate-card-wizard'

interface Props {
  onSubmit: (data: Record<string, unknown>) => void
  saving: boolean
}

export function StepRateCard({ onSubmit, saving }: Props) {
  const handleWizardSubmit = (data: RateCardPayload) => {
    onSubmit(data as unknown as Record<string, unknown>)
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        Set up your rate card in 4 short steps. You can skip any section and finish it later in Settings.
      </p>
      <RateCardWizard onSubmit={handleWizardSubmit} saving={saving} />
    </div>
  )
}
