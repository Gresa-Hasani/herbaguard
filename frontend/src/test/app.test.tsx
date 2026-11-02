import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import { FALLBACK_DISCLAIMER } from '../lib/constants'
import { mockFetch, renderWithProviders } from './render'

const META = {
  name: 'HerbaGuard',
  version: '0.1.0',
  environment: 'test',
  api_version: 'v1',
  disclaimer: 'Disclaimer text served by the API.',
}

describe('application shell', () => {
  it('shows the disclaimer from the API and reports a healthy backend', async () => {
    mockFetch({
      '/api/v1/meta': [200, META],
      '/api/v1/health/ready': [200, { status: 'ok', checks: [] }],
    })
    renderWithProviders(<AppRoutes />)

    const disclaimer = screen.getByRole('complementary', { name: 'Medical disclaimer' })
    expect(await within(disclaimer).findByText(META.disclaimer)).toBeInTheDocument()
    expect(await screen.findByText('Service online')).toBeInTheDocument()
  })

  it('keeps the fallback disclaimer and reports an outage when the API is down', async () => {
    mockFetch({})
    renderWithProviders(<AppRoutes />)

    expect(await screen.findByText('Service unavailable')).toBeInTheDocument()
    const disclaimer = screen.getByRole('complementary', { name: 'Medical disclaimer' })
    expect(disclaimer).toHaveTextContent(FALLBACK_DISCLAIMER)
  })

  it('reports a degraded backend when the readiness probe returns 503', async () => {
    mockFetch({
      '/api/v1/meta': [200, META],
      '/api/v1/health/ready': [
        503,
        { error: { code: 'service_unavailable', message: 'Database unreachable' } },
      ],
    })
    renderWithProviders(<AppRoutes />)
    expect(await screen.findByText('Service unavailable')).toBeInTheDocument()
  })

  it('renders every module as a clearly labelled placeholder', () => {
    mockFetch({})
    renderWithProviders(<AppRoutes />, { route: '/interactions' })

    expect(screen.getByRole('heading', { level: 1, name: 'Interaction Check' })).toBeInTheDocument()
    expect(screen.getByText(/Not available yet/)).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getAllByRole('link')).toHaveLength(5)
  })

  it('shows a not-found page for unknown routes', () => {
    mockFetch({})
    renderWithProviders(<AppRoutes />, { route: '/nowhere' })
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
