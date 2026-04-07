import { useState } from 'react'
import type { ChatMessage } from '../../types/proposal'

interface FileInfo {
  type: string
  filename: string
  size?: number
  url?: string
  theme?: string
}

interface Props {
  message: ChatMessage
  proposalId: string
}

const FILE_ICONS: Record<string, string> = {
  site: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
  docx: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  html: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
  pdf: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z',
  email: 'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
}

const FILE_LABELS: Record<string, string> = {
  site: 'Interactive Proposal Site',
  docx: 'Word Document',
  html: 'Print-Ready HTML',
  pdf: 'PDF',
  email: 'Email Drafts',
}

function formatSize(bytes: number): string {
  if (bytes > 1048576) return `${(bytes / 1048576).toFixed(1)} MB`
  if (bytes > 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

export function OutputReadyCard({ message, proposalId }: Props) {
  const extra = message.extra_data as Record<string, unknown>
  const files = (extra?.files || []) as FileInfo[]
  const emailConfident = extra?.email_confident as string
  const emailWarm = extra?.email_warm as string
  const [showEmail, setShowEmail] = useState<'confident' | 'warm' | null>(null)

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] w-full rounded-2xl border border-green-200 bg-green-50 px-5 py-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <span className="text-base font-semibold text-green-900">Proposal Ready</span>
        </div>

        <p className="text-sm text-green-800 mb-4">{message.content}</p>

        {/* Interactive site preview button */}
        {files.find(f => f.type === 'site') && (
          <a
            href={files.find(f => f.type === 'site')?.url || `/p/${proposalId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 rounded-xl bg-stone-900 text-white px-4 py-3.5 mb-3 hover:bg-stone-800 transition-colors font-medium text-sm"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={FILE_ICONS.site} />
            </svg>
            Preview Interactive Proposal Site
            <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        )}

        {/* File download buttons */}
        <div className="space-y-2">
          {files.filter(f => f.type !== 'site').map((file) => (
            <a
              key={file.filename}
              href={`/api/v1/dl/${proposalId}/${file.filename}`}
              download
              className="flex items-center gap-3 rounded-lg border border-green-200 bg-white px-4 py-3 hover:bg-green-50 transition-colors"
            >
              <svg className="w-5 h-5 text-green-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={FILE_ICONS[file.type] || FILE_ICONS.docx} />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-stone-900">{FILE_LABELS[file.type] || file.type.toUpperCase()}</p>
                <p className="text-xs text-stone-500">{file.filename}{file.size ? ` — ${formatSize(file.size)}` : ''}</p>
              </div>
              <svg className="w-4 h-4 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </a>
          ))}
        </div>

        {/* Email drafts */}
        {(emailConfident || emailWarm) && (
          <div className="mt-4">
            <p className="text-sm font-medium text-green-900 mb-2">Email Drafts</p>
            <div className="flex gap-2 mb-2">
              <button
                onClick={() => setShowEmail(showEmail === 'confident' ? null : 'confident')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  showEmail === 'confident' ? 'bg-green-600 text-white' : 'bg-white border border-green-200 text-green-700'
                }`}
              >
                Confident
              </button>
              <button
                onClick={() => setShowEmail(showEmail === 'warm' ? null : 'warm')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  showEmail === 'warm' ? 'bg-green-600 text-white' : 'bg-white border border-green-200 text-green-700'
                }`}
              >
                Warm
              </button>
            </div>
            {showEmail && (
              <div className="rounded-lg border border-green-200 bg-white p-3 text-sm text-stone-700 whitespace-pre-wrap max-h-60 overflow-y-auto">
                {showEmail === 'confident' ? emailConfident : emailWarm}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
