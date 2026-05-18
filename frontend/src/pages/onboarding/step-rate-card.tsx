import { RateCardWizard, type RateCardPayload } from '../../components/rate-card-wizard'

interface Props {
  onSubmit: (data: RateCardPayload) => void
  saving: boolean
}

export function StepRateCard({ onSubmit, saving }: Props) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        Set up your rate card in 4 short steps. You can skip any section and finish it later in Settings.
      </p>
      <RateCardWizard onSubmit={onSubmit} saving={saving} />
    </div>
  )
}
