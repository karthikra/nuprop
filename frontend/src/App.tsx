import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/auth-store'
import { AppShell } from './components/layout/app-shell'
import { Dashboard } from './pages/dashboard'
import { LoginPage } from './pages/auth/login'
import { RegisterPage } from './pages/auth/register'
import { OnboardingPage } from './pages/onboarding'
import { ClientListPage } from './pages/clients/list'
import { ClientDetailPage } from './pages/clients/detail'
import { ProposalListPage } from './pages/proposals/list'
import { NewProposalPage } from './pages/proposals/new'
import { BuilderPage } from './pages/proposals/builder'
import { AnalyticsOverviewPage } from './pages/analytics/overview'
import { AnalyticsDetailPage } from './pages/analytics/detail'
import { RateCardEditorPage } from './pages/rate-card/editor'
import { TemplateListPage } from './pages/templates/list'
import { TemplateEditorPage } from './pages/templates/editor'
import { AgencySettingsPage } from './pages/settings/agency'
import { GmailCallbackPage } from './pages/settings/gmail-callback'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  const isLoading = useAuthStore((s) => s.isLoading)
  const agency = useAuthStore((s) => s.agency)

  if (isLoading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="animate-spin h-6 w-6 border-2 border-stone-900 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />
  if (agency && !agency.onboarding_complete) return <Navigate to="/onboarding" replace />

  return <Outlet />
}

function AuthRoute() {
  const token = useAuthStore((s) => s.token)
  const isLoading = useAuthStore((s) => s.isLoading)

  if (isLoading) return null
  if (token) return <Navigate to="/" replace />

  return <Outlet />
}

export default function App() {
  const initialize = useAuthStore((s) => s.initialize)

  useEffect(() => {
    initialize()
  }, [initialize])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public auth routes */}
          <Route element={<AuthRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
          </Route>

          {/* Onboarding (authenticated but not onboarded) */}
          <Route path="/onboarding" element={<OnboardingPage />} />

          {/* Protected app routes */}
          <Route element={<ProtectedRoute />}>
            {/* Builder page — own layout, no AppShell sidebar */}
            <Route path="/proposals/:id" element={<BuilderPage />} />

            {/* Standard app pages with sidebar */}
            <Route element={<AppShell />}>
              <Route index element={<Dashboard />} />
              <Route path="/proposals" element={<ProposalListPage />} />
              <Route path="/proposals/new" element={<NewProposalPage />} />
              <Route path="/clients" element={<ClientListPage />} />
              <Route path="/clients/:id" element={<ClientDetailPage />} />
              <Route path="/rate-card" element={<RateCardEditorPage />} />
              <Route path="/templates" element={<TemplateListPage />} />
              <Route path="/templates/:id" element={<TemplateEditorPage />} />
              <Route path="/analytics" element={<AnalyticsOverviewPage />} />
              <Route path="/analytics/:id" element={<AnalyticsDetailPage />} />
              <Route path="/settings" element={<AgencySettingsPage />} />
              <Route path="/settings/gmail-callback" element={<GmailCallbackPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

