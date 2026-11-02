import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { ROUTER_FUTURE_FLAGS } from '../lib/router'

/** Render with a fresh QueryClient (no retries) and an in-memory router. */
export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]} future={ROUTER_FUTURE_FLAGS}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Mock global fetch with a map of path → [status, body]. Unknown paths reject. */
export function mockFetch(routes: Record<string, [number, unknown]>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = new URL(url, 'http://localhost').pathname
    const route = routes[path]
    if (!route) throw new TypeError(`Network error for ${path}`)
    const [status, body] = route
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}
