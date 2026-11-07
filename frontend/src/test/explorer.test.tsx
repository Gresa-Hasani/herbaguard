import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import {
  DETAIL,
  EMPTY_LABEL_PAGE,
  EVIDENCE_PAGE,
  LABEL,
  LABEL_PAGE,
  META,
  TAXON_PAGE,
  WFO,
} from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const EXPLORER_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
  '/api/v1/plants': [200, TAXON_PAGE] as [number, unknown],
  [`/api/v1/plants/${WFO}`]: [200, DETAIL] as [number, unknown],
  [`/api/v1/evidence?wfo_id=${WFO}&limit=50`]: [200, EVIDENCE_PAGE] as [number, unknown],
  [`/api/v1/plants/${WFO}/product-labels?limit=20`]: [200, LABEL_PAGE] as [number, unknown],
}

describe('herb explorer', () => {
  it('renders taxonomy, regulatory information, clinical evidence and a separated DSLD section', async () => {
    mockFetch(EXPLORER_ROUTES)
    renderWithProviders(<AppRoutes />, { route: `/explorer?wfo=${WFO}` })

    expect(
      await screen.findByRole('heading', { level: 2, name: /Hypericum perforatum/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Hypericaceae/)).toBeInTheDocument()
    expect(screen.getByText(/part: flowering top/i)).toBeInTheDocument()

    const regulatory = screen.getByRole('region', { name: 'Regulatory information' })
    expect(
      within(regulatory).getAllByText(/European Union herbal monograph on Hypericum perforatum/i)
        .length,
    ).toBeGreaterThan(0)
    expect(within(regulatory).getByText('Traditional use')).toBeInTheDocument()

    const evidence = screen.getByRole('region', { name: 'Indexed clinical evidence' })
    expect(
      within(evidence).getByRole('link', {
        name: /European Union herbal monograph on Hypericum perforatum/i,
      }),
    ).toHaveAttribute('href', 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba')
    expect(within(evidence).getByText(/Regulatory monograph/i)).toBeInTheDocument()
    expect(within(evidence).queryByText('SJW 300')).not.toBeInTheDocument()

    const labels = screen.getByRole('region', { name: 'Product labels (NIH DSLD)' })
    expect(
      within(labels).getByRole('heading', { name: 'Product labels (NIH DSLD)' }),
    ).toBeInTheDocument()
    expect(
      within(labels).getByText(
        'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
      ),
    ).toBeInTheDocument()
    expect(within(labels).getByText('SJW 300')).toBeInTheDocument()
    expect(within(labels).getByText('Example Botanicals · DSLD ID 1001')).toBeInTheDocument()
    expect(
      within(labels).getByText('“Consult your physician if you take anticoagulants.”'),
    ).toBeInTheDocument()
    expect(within(labels).getAllByText('Licence unverified').length).toBeGreaterThanOrEqual(2)

    expect(within(evidence).queryByText(/Consult your physician/i)).not.toBeInTheDocument()
    expect(within(regulatory).queryByText(/Consult your physician/i)).not.toBeInTheDocument()
  })

  it('states zero label coverage without turning it into a safety claim', async () => {
    mockFetch({
      ...EXPLORER_ROUTES,
      [`/api/v1/plants/${WFO}/product-labels?limit=20`]: [200, EMPTY_LABEL_PAGE],
    })
    renderWithProviders(<AppRoutes />, { route: `/explorer?wfo=${WFO}` })

    const labels = await screen.findByRole('region', { name: 'Product labels (NIH DSLD)' })
    expect(await within(labels).findByText('No NIH DSLD label matched this plant')).toBeInTheDocument()
    expect(
      within(labels).getByText(/does not show that products containing this plant are safe/i),
    ).toBeInTheDocument()
    expect(within(labels).queryByText(LABEL.precautions[0])).not.toBeInTheDocument()
    expect(within(labels).getByText(/Licence unverified/i)).toBeInTheDocument()
  })

  it('does not merge product labels into clinical evidence when the label endpoint fails', async () => {
    mockFetch({
      ...EXPLORER_ROUTES,
      [`/api/v1/plants/${WFO}/product-labels?limit=20`]: [
        503,
        { error: { code: 'unavailable', message: 'DSLD store unavailable' } },
      ],
    })
    renderWithProviders(<AppRoutes />, { route: `/explorer?wfo=${WFO}` })

    expect(await screen.findByText(/product-label endpoint is unavailable/i)).toBeInTheDocument()
    const evidence = screen.getByRole('region', { name: 'Indexed clinical evidence' })
    expect(within(evidence).queryByText('SJW 300')).not.toBeInTheDocument()
  })
})
