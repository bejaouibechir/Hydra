import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useMemo } from 'react'
import { ThemeContext } from '@/hooks/useThemeContext'
import { useTheme } from '@/hooks/useTheme'
import { NotificationProvider } from '@/contexts/NotificationContext'
import AppLayout from '@/components/layout/AppLayout'
import RouteErrorBoundary from '@/components/ui/ErrorBoundary'
import Overview      from '@/pages/Overview'
import ProjectDetail from '@/pages/projects/ProjectDetail'
import Runs          from '@/pages/runs/Runs'
import RunDetail     from '@/pages/runs/RunDetail'
import Templates     from '@/pages/Templates'
import Insights      from '@/pages/Insights'
import Settings        from '@/pages/Settings'
import Help            from '@/pages/Help'
import WorkflowEditor  from '@/pages/workflows/WorkflowEditor'

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1 } },
})

function ThemedApp() {
  const theme = useTheme()
  const ctx = useMemo(() => theme, [theme.themeId])

  return (
    <ThemeContext.Provider value={ctx}>
      <NotificationProvider>
      <BrowserRouter>
        <RouteErrorBoundary>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="overview"              element={<Overview />} />
            <Route path="projects"              element={<Navigate to="/overview" replace />} />
            <Route path="projects/:projectId"   element={<ProjectDetail />} />
            <Route path="runs"                  element={<Runs />} />
            <Route path="runs/:runId"           element={<RunDetail />} />
            <Route path="templates"             element={<Templates />} />
            <Route path="insights"              element={<Insights />} />
            <Route path="workflows/:workflowId"  element={<WorkflowEditor />} />
            <Route path="settings/*"            element={<Settings />} />
            <Route path="help"                  element={<Help />} />
          </Route>
        </Routes>
        </RouteErrorBoundary>
      </BrowserRouter>
      </NotificationProvider>
    </ThemeContext.Provider>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ThemedApp />
    </QueryClientProvider>
  )
}
