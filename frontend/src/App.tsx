import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { PublicLayout } from './components/PublicLayout'
import { AboutPage } from './pages/AboutPage'
import { AssistantPage } from './pages/AssistantPage'
import { ExplorerPage } from './pages/ExplorerPage'
import { HomePage } from './pages/HomePage'
import { InteractionPage } from './pages/InteractionPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SourcesPage } from './pages/SourcesPage'

export function AppRoutes() {
  return (
    <Routes>
      {/* Public product experience */}
      <Route element={<PublicLayout />}>
        <Route index element={<HomePage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="sources" element={<SourcesPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      {/* Application experience */}
      <Route element={<AppLayout />}>
        <Route path="interactions" element={<InteractionPage />} />
        <Route path="explorer" element={<ExplorerPage />} />
        <Route path="assistant" element={<AssistantPage />} />
      </Route>
    </Routes>
  )
}

export function App() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <AppRoutes />
    </QueryClientProvider>
  )
}
