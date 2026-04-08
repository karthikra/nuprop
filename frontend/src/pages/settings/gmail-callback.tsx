import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useGmailCallback } from '../../api/connectors'

export function GmailCallbackPage() {
  const [searchParams] = useSearchParams()
  const callback = useGmailCallback()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')

    if (!code) {
      setStatus('error')
      return
    }

    callback.mutate(
      { code, state: state || '' },
      {
        onSuccess: () => {
          setStatus('success')
          // Close popup after brief delay, parent will refetch status
          setTimeout(() => {
            if (window.opener) {
              window.opener.focus()
            }
            window.close()
          }, 1500)
        },
        onError: () => {
          setStatus('error')
        },
      }
    )
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-stone-50 flex items-center justify-center">
      <div className="text-center">
        {status === 'processing' && (
          <>
            <div className="animate-spin h-8 w-8 border-2 border-stone-900 border-t-transparent rounded-full mx-auto" />
            <p className="mt-4 text-sm text-stone-500">Connecting Gmail...</p>
          </>
        )}
        {status === 'success' && (
          <>
            <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="mt-4 text-sm font-medium text-stone-900">Gmail connected</p>
            <p className="text-xs text-stone-500 mt-1">This window will close automatically.</p>
          </>
        )}
        {status === 'error' && (
          <>
            <p className="text-sm text-red-600">Failed to connect Gmail.</p>
            <button onClick={() => window.close()} className="mt-2 text-xs text-stone-500 underline">Close this window</button>
          </>
        )}
      </div>
    </div>
  )
}
