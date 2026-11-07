import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import type { Page, PlantCoverage, TaxonCoverage, TaxonSummary } from '../lib/types'
import {
  DETAIL,
  EMPTY_LABEL_PAGE,
  EVIDENCE_PAGE,
  META,
  TAXON,
  WFO,
} from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const BASE = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
}

function taxon(n: number, overrides: Partial<TaxonSummary> = {}): TaxonSummary {
  const id = `wfo-${String(n).padStart(10, '0')}`
  return {
    wfo_id: id,
    scientific_name: `Plantago species${n}`,
    authorship: 'L.',
    family: 'Plantaginaceae',
    herbs: [{ pharmaceutical_name: `Plantaginis herba ${n}`, common_name: `Plant ${n}`, plant_part: 'leaf' }],
    matched_name: null,
    ...overrides,
  }
}

function coverageRow(t: TaxonSummary, overrides: Partial<TaxonCoverage> = {}): TaxonCoverage {
  return {
    wfo_id: t.wfo_id,
    scientific_name: t.scientific_name,
    family: t.family,
    taxonomic_status: 'accepted',
    monograph_documents: 1,
    fact_sheet_items: 0,
    drug_label_mentions: 0,
    literature_clinical_items: 3,
    literature_interaction_items: 2,
    dsld_products: 0,
    supplementary_sources: {},
    active_interaction_statements: 0,
    ...overrides,
  }
}

function pageOf(items: TaxonSummary[], total: number, offset = 0): Page<TaxonSummary> {
  return { items, total, limit: 24, offset }
}

describe('herb explorer: full index with server paging', () => {
  it('shows the real total, loads further pages and never calls the list a sample', async () => {
    const user = userEvent.setup()
    const all = Array.from({ length: 30 }, (_, i) => taxon(i + 1))
    mockFetch({
      ...BASE,
      '/api/v1/plants?limit=24&offset=0': [200, pageOf(all.slice(0, 24), 30)],
      '/api/v1/plants?limit=24&offset=24': [200, pageOf(all.slice(24), 30, 24)],
    })
    const calls: string[] = []
    const spy = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
    renderWithProviders(<AppRoutes />, { route: '/explorer' })

    expect(await screen.findByText('Showing 24 of 30 supported plants')).toBeInTheDocument()
    expect(screen.queryByText(/sample of supported plants/i)).not.toBeInTheDocument()
    expect(screen.getByText('Plantago species24')).toBeInTheDocument()
    expect(screen.queryByText('Plantago species25')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Load more (24 of 30)' }))
    expect(await screen.findByText('Plantago species30')).toBeInTheDocument()
    expect(screen.getByText('Showing all 30 supported plants')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()

    for (const call of spy.calls) calls.push(String(call[0]))
    expect(calls.some((url) => url.includes('/api/v1/plants?limit=24&offset=24'))).toBe(true)
  })

  it('keeps every taxon that shares a common name and asks the user to choose by scientific name', async () => {
    const hawthorn = ['azarolus', 'laevigata', 'monogyna'].map((epithet, i) =>
      taxon(100 + i, {
        scientific_name: `Crataegus ${epithet}`,
        herbs: [{ pharmaceutical_name: 'Crataegi folium cum flore', common_name: 'Hawthorn', plant_part: 'leaf and flower' }],
        matched_name: { name: 'Hawthorn', name_type: 'common', language: 'en', source_code: 'wfo' },
      }),
    )
    mockFetch({
      ...BASE,
      '/api/v1/plants?limit=24&offset=0': [200, pageOf([taxon(1)], 1)],
      '/api/v1/plants?limit=24&offset=0&q=hawthorn': [200, pageOf(hawthorn, 3)],
    })
    const user = userEvent.setup()
    renderWithProviders(<AppRoutes />, { route: '/explorer' })
    await user.type(await screen.findByLabelText('Find a herb'), 'hawthorn')

    expect(
      await screen.findByText('This name matches more than one plant', {}, { timeout: 3000 }),
    ).toBeInTheDocument()
    expect(screen.getByText('3 matching plant record(s)')).toBeInTheDocument()
    for (const name of ['Crataegus azarolus', 'Crataegus laevigata', 'Crataegus monogyna']) {
      expect(screen.getByText(name)).toBeInTheDocument()
    }
    expect(screen.getAllByText(/Matched common name “Hawthorn”/)).toHaveLength(3)
  })

  it('searches by scientific name through the API and reports no match honestly', async () => {
    mockFetch({
      ...BASE,
      '/api/v1/plants?limit=24&offset=0': [200, pageOf([taxon(1)], 1)],
      '/api/v1/plants?limit=24&offset=0&q=zzzz': [200, pageOf([], 0)],
    })
    const user = userEvent.setup()
    renderWithProviders(<AppRoutes />, { route: '/explorer' })
    await user.type(await screen.findByLabelText('Find a herb'), 'zzzz')
    expect(await screen.findByText('No matching plant', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('0 matching plant record(s)')).toBeInTheDocument()
  })
})

describe('herb explorer: coverage by kind of material', () => {
  const full = taxon(1, { scientific_name: 'Hypericum perforatum' })
  const bare = taxon(2, { scientific_name: 'Plantago bare' })
  const rows: TaxonCoverage[] = [
    coverageRow(full, {
      monograph_documents: 3,
      fact_sheet_items: 2,
      drug_label_mentions: 4,
      dsld_products: 120,
      supplementary_sources: { ddid: 'resolved', supp_ai: 'candidate' },
    }),
    coverageRow(bare, {
      monograph_documents: 0,
      literature_clinical_items: 0,
      literature_interaction_items: 0,
    }),
  ]
  const coverage: PlantCoverage = { total: 2, items: rows }
  const routes = {
    ...BASE,
    '/api/v1/plants?limit=24&offset=0': [200, pageOf([full, bare], 2)] as [number, unknown],
    '/api/v1/coverage/plants': [200, coverage] as [number, unknown],
  }

  it('reports counts computed from the stored rows and a per-source matrix', async () => {
    const user = userEvent.setup()
    mockFetch(routes)
    renderWithProviders(<AppRoutes />, { route: '/explorer' })

    const summary = await screen.findByRole('region', { name: 'Dataset coverage' })
    expect(within(summary).getByText('Plants in the index').parentElement).toHaveTextContent(/2\s*\/\s*2/)
    expect(within(summary).getByText('With regulatory material').parentElement).toHaveTextContent(/1\s*\/\s*2/)
    expect(within(summary).getByText('With indexed literature').parentElement).toHaveTextContent(/1\s*\/\s*2/)
    expect(within(summary).getByText('With product labels').parentElement).toHaveTextContent(/1\s*\/\s*2/)

    await user.click(within(summary).getByText('Coverage by source'))
    const table = within(summary).getByRole('table')
    const labelsRow = within(table).getByText('NIH DSLD product labels').closest('tr') as HTMLElement
    expect(labelsRow).toHaveTextContent('1 / 2')
    expect(labelsRow).toHaveTextContent('Not clinical evidence; never used for classification.')
    const ddidRow = within(table).getByText('DDID experimental records').closest('tr') as HTMLElement
    expect(ddidRow).toHaveTextContent('1 / 2')
    const suppRow = within(table).getByText('Supp.AI mentions').closest('tr') as HTMLElement
    expect(suppRow).toHaveTextContent('0 / 2')
    expect(suppRow).toHaveTextContent('only a candidate mapping, which is not used as a match')
  })

  it('shows explicit "none" states on plant tiles and keeps labels apart from evidence', async () => {
    mockFetch(routes)
    renderWithProviders(<AppRoutes />, { route: '/explorer' })
    const fullTile = (await screen.findByText('Hypericum perforatum')).closest('button') as HTMLElement
    expect(within(fullTile).getByText('Regulatory')).toBeInTheDocument()
    expect(within(fullTile).getByText('Indexed literature')).toBeInTheDocument()
    expect(within(fullTile).getByText('Product labels')).toBeInTheDocument()

    const bareTile = screen.getByText('Plantago bare').closest('button') as HTMLElement
    expect(within(bareTile).getByText('No regulatory record')).toBeInTheDocument()
    expect(within(bareTile).getByText('No indexed literature')).toBeInTheDocument()
    expect(within(bareTile).getByText('No product label')).toBeInTheDocument()
  })

  it('states what is and is not stored for a plant with no regulatory, literature or label records', async () => {
    const detail = { ...DETAIL, wfo_id: bare.wfo_id, scientific_name: 'Plantago bare', monographs: [], indications: [] }
    mockFetch({
      ...routes,
      [`/api/v1/plants/${bare.wfo_id}`]: [200, detail],
      [`/api/v1/evidence?wfo_id=${bare.wfo_id}&limit=50`]: [200, { ...EVIDENCE_PAGE, items: [], total: 0 }],
      [`/api/v1/plants/${bare.wfo_id}/product-labels?limit=20`]: [200, EMPTY_LABEL_PAGE],
    })
    renderWithProviders(<AppRoutes />, { route: `/explorer?wfo=${bare.wfo_id}` })

    const strip = await screen.findByRole('region', { name: 'Coverage for this plant' })
    expect(within(strip).getByText(/Accepted species in World Flora Online/)).toBeInTheDocument()
    expect(within(strip).getByText(/A taxonomic record is identity information, not evidence/)).toBeInTheDocument()
    expect(
      within(strip).getByText(/No regulatory record stored \(EMA monograph, NCCIH fact sheet or openFDA label mention\)/),
    ).toBeInTheDocument()
    expect(within(strip).getByText('No PubMed records are indexed for this plant.')).toBeInTheDocument()
    expect(
      within(strip).getByText(/No NIH DSLD label matched this plant\. This is a coverage statement, not a safety statement\./),
    ).toBeInTheDocument()

    expect(await screen.findByText('No monograph stored')).toBeInTheDocument()
    expect(await screen.findByText('No indexed evidence')).toBeInTheDocument()
    const labels = await screen.findByRole('region', { name: 'Product labels (NIH DSLD)' })
    expect(await within(labels).findByText('No NIH DSLD label matched this plant')).toBeInTheDocument()
  })

  it('marks manufacturer labels as not clinical evidence for a plant that has them', async () => {
    mockFetch({
      ...routes,
      [`/api/v1/plants/${full.wfo_id}`]: [200, { ...DETAIL, wfo_id: full.wfo_id }],
      [`/api/v1/evidence?wfo_id=${full.wfo_id}&limit=50`]: [200, EVIDENCE_PAGE],
      [`/api/v1/plants/${full.wfo_id}/product-labels?limit=20`]: [200, EMPTY_LABEL_PAGE],
    })
    renderWithProviders(<AppRoutes />, { route: `/explorer?wfo=${full.wfo_id}` })
    const strip = await screen.findByRole('region', { name: 'Coverage for this plant' })
    expect(within(strip).getByText(/120 DSLD products list this plant/)).toBeInTheDocument()
    expect(within(strip).getByText('Manufacturer information, not clinical evidence.')).toBeInTheDocument()
    expect(within(strip).getByText(/DDID \(resolved\), Supp\.AI \(candidate\)/)).toBeInTheDocument()
    expect(within(strip).getByText(/a candidate mapping is not treated as a match/)).toBeInTheDocument()
  })

  it('still works when the coverage endpoint is unavailable', async () => {
    mockFetch({
      ...BASE,
      '/api/v1/plants?limit=24&offset=0': [200, pageOf([taxon(1, TAXON)], 1)],
      [`/api/v1/plants/${WFO}`]: [200, DETAIL],
      [`/api/v1/evidence?wfo_id=${WFO}&limit=50`]: [200, EVIDENCE_PAGE],
      [`/api/v1/plants/${WFO}/product-labels?limit=20`]: [200, EMPTY_LABEL_PAGE],
    })
    renderWithProviders(<AppRoutes />, { route: '/explorer' })
    expect(await screen.findByText('Showing all 1 supported plants')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Dataset coverage' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/Loading/)).not.toBeInTheDocument())
  })
})
