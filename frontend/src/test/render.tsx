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

export interface MockRequest {
  url: URL
  method: string
  body: unknown
  signal: AbortSignal | null
}

export type MockRoute =
  | [number, unknown]
  | 'hang'
  | ((request: MockRequest) => [number, unknown] | Promise<[number, unknown]>)

/**
 * Mock global fetch with a map. Keys may be a full path with query or just the pathname.
 * The first match wins, checking "METHOD full-path" and "full-path" before bare paths.
 */
export function mockFetch(routes: Record<string, MockRoute>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const signal = init?.signal ?? null
    let body: unknown = null
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body)
      } catch {
        body = init.body
      }
    }

    const keys = [
      `${method} ${url.pathname}${url.search}`,
      `${method} ${url.pathname}`,
      `${url.pathname}${url.search}`,
      url.pathname,
    ]
    const key = keys.find((candidate) => candidate in routes)
    const route = key ? routes[key] : undefined

    if (route === undefined) throw new TypeError(`Network error for ${url.pathname}`)
    if (route === 'hang') {
      return new Promise<Response>((_resolve, reject) => {
        const abort = () => reject(new DOMException('Aborted', 'AbortError'))
        if (signal?.aborted) abort()
        else signal?.addEventListener('abort', abort, { once: true })
      })
    }

    const [status, payload] =
      typeof route === 'function' ? await route({ url, method, body, signal }) : route
    return new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}
