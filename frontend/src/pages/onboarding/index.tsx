import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth-store'
import { StepProfile } from './step-profile'
import { StepRateCard } from './step-rate-card'
import { StepVoice } from './step-voice'
import { StepComplete } from './step-complete'

const STEPS = ['Profile', 'Rate Card', 'Voice', 'Complete']

export function OnboardingPage() {
  const navigate = useNavigate()
  const fetchAgency = useAuthStore((s) => s.fetchAgency)
  const [currentStep, setCurrentStep] = useState(1)
  const [saving, setSaving] = useState(false)

  const submitStep = async (step: number, data: Record<string, unknown>) => {
    setSaving(true)
    try {
      await api.post('/agencies/me/onboarding', { step, data })
      if (step === 4) {
        await fetchAgency()
        navigate('/')
      } else {
        setCurrentStep(step + 1)
      }
    } catch (err) {
      console.error('Onboarding step failed:', err)
    }
    setSaving(false)
  }

  return (
    <div className="min-h-screen bg-stone-50 flex flex-col items-center pt-16 px-4">
      <h1 className="text-2xl font-semibold text-stone-900">Set up your agency</h1>

      {/* Progress bar */}
      <div className="mt-8 flex items-center gap-2 w-full max-w-md">
        {STEPS.map((label, i) => (
          <div key={label} className="flex-1">
            <div
              className={`h-1.5 rounded-full ${
                i + 1 <= currentStep ? 'bg-stone-900' : 'bg-stone-200'
              }`}
            />
            <p className={`mt-1 text-xs ${
              i + 1 <= currentStep ? 'text-stone-900 font-medium' : 'text-stone-400'
            }`}>
              {label}
            </p>
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="mt-8 w-full max-w-md">
        {currentStep === 1 && <StepProfile onSubmit={(data) => submitStep(1, data)} saving={saving} />}
        {currentStep === 2 && <StepRateCard onSubmit={(data) => submitStep(2, data)} saving={saving} />}
        {currentStep === 3 && <StepVoice onSubmit={(data) => submitStep(3, data)} saving={saving} />}
        {currentStep === 4 && <StepComplete onSubmit={() => submitStep(4, {})} saving={saving} />}
      </div>
    </div>
  )
}
