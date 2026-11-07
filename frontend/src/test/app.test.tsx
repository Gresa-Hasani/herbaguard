import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import { FALLBACK_DISCLAIMER } from '../lib/constants'
import type { SourceRow } from '../lib/types'
import { META, SOURCES, TAXON_PAGE } from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const BASE_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
  '/api/v1/sources': [200, SOURCES] as [number, unknown],
  '/api/v1/plants': [200, TAXON_PAGE] as [number, unknown],
}

describe('application shell', () => {
  it('shows the disclaimer from the API and reports a healthy backend', async () => {
    mockFetch(BASE_ROUTES)
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

  it('reports an unavailable backend when the readiness probe fails', async () => {
    mockFetch({
      ...BASE_ROUTES,
      '/api/v1/health/ready': [
        503,
        { error: { code: 'service_unavailable', message: 'Database unreachable' } },
      ],
    })
    renderWithProviders(<AppRoutes />)
    expect(await screen.findByText('Service unavailable')).toBeInTheDocument()
  })
})

describe('navigation and pages', () => {
  it('renders the landing page without registry statistics and with the public navigation', async () => {
    const fetchSpy = mockFetch(BASE_ROUTES)
    renderWithProviders(<AppRoutes />)

    expect(
      screen.getByRole('heading', { level: 1, name: /Herb–drug evidence you can trace/i }),
    ).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'How it works',
      'Evidence-first',
      'About',
      'Sources & methodology',
      'Open workspace',
    ])

    // Calls to action reach the workspace tools.
    expect(screen.getAllByRole('link', { name: 'Check an interaction' })[0]).toHaveAttribute(
      'href',
      '/interactions',
    )
    expect(screen.getAllByRole('link', { name: 'Explore medicinal plants' })[0]).toHaveAttribute(
      'href',
      '/explorer',
    )

    // Four evidence tiers, with manufacturer labels explicitly not clinical evidence.
    expect(screen.getByText('Regulatory & government evidence')).toBeInTheDocument()
    expect(screen.getByText('Clinical & scientific literature')).toBeInTheDocument()
    expect(screen.getByText('Supplementary research material')).toBeInTheDocument()
    expect(screen.getByText('Manufacturer product-label information')).toBeInTheDocument()
    expect(screen.getByText('Not clinical evidence')).toBeInTheDocument()

    // The footer offers product pages and transparency pages, not the raw API documentation.
    const footer = screen.getByRole('contentinfo')
    expect(within(footer).getByRole('link', { name: 'Sources & methodology' })).toBeInTheDocument()
    expect(within(footer).getByRole('link', { name: 'About' })).toBeInTheDocument()
    expect(within(footer).queryByText(/API documentation/i)).not.toBeInTheDocument()
    expect(
      within(footer)
        .queryAllByRole('link')
        .some((link) => /\/api\/docs/.test(link.getAttribute('href') ?? '')),
    ).toBe(false)

    // No source counts, dataset totals or invented metrics on the landing page.
    expect(screen.queryByText('Sources registered')).not.toBeInTheDocument()
    expect(screen.queryByText(/source records/i)).not.toBeInTheDocument()
    expect(screen.queryByText('15,626')).not.toBeInTheDocument()
    expect(
      fetchSpy.mock.calls.some(([input]) => String(input).includes('/api/v1/sources')),
    ).toBe(false)
  })

  it.each([
    ['/interactions', 'Interaction Checker'],
    ['/explorer', 'Herb Explorer'],
    ['/assistant', 'Evidence Assistant'],
    ['/about', 'About HerbaGuard'],
    ['/sources', 'Sources & methodology'],
  ])('navigates to %s and renders its real page', async (route, heading) => {
    mockFetch(BASE_ROUTES)
    renderWithProviders(<AppRoutes />, { route })
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
    expect(screen.queryByText(/Not available yet/)).not.toBeInTheDocument()
  })

  it('moves from the public landing page into the workspace and between tools', async () => {
    const user = userEvent.setup()
    mockFetch(BASE_ROUTES)
    renderWithProviders(<AppRoutes />)

    await user.click(screen.getByRole('link', { name: 'Open workspace' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Interaction Checker' }),
    ).toBeInTheDocument()

    const rail = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(rail).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Interaction Checker',
      'Herb Explorer',
      'Evidence Assistant',
    ])
    expect(within(rail).getByRole('link', { name: 'Interaction Checker' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    await user.click(screen.getByRole('link', { name: 'Herb Explorer' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Herb Explorer' })).toBeInTheDocument()
    expect(within(rail).getByRole('link', { name: 'Herb Explorer' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    await user.click(screen.getByRole('link', { name: 'Evidence Assistant' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Evidence Assistant' }),
    ).toBeInTheDocument()

    // The mobile bar offers the same three tools with short labels.
    const mobile = screen.getByRole('navigation', { name: 'Workspace (mobile)' })
    expect(within(mobile).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Checker',
      'Explorer',
      'Assistant',
    ])
  })

  it('links the workspace back to the public pages', async () => {
    const user = userEvent.setup()
    mockFetch(BASE_ROUTES)
    renderWithProviders(<AppRoutes />, { route: '/interactions' })

    await user.click(screen.getAllByRole('link', { name: 'Sources & methodology' })[0])
    expect(
      screen.getByRole('heading', { level: 1, name: 'Sources & methodology' }),
    ).toBeInTheDocument()
  })

  it('shows a not-found page for unknown routes', () => {
    mockFetch(BASE_ROUTES)
    renderWithProviders(<AppRoutes />, { route: '/nowhere' })
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

const row = (overrides: Partial<SourceRow> & Pick<SourceRow, 'code' | 'name'>): SourceRow => ({
  provider: 'Provider',
  homepage_url: `https://example.org/${overrides.code}`,
  is_official: true,
  licence: null,
  licence_status: 'to_verify',
  redistributable: false,
  last_run_status: 'succeeded',
  last_run_finished_at: null,
  records: 1,
  licence_url: null,
  attribution: null,
  access_method: 'download',
  latest_retrieved_at: null,
  latest_source_version: null,
  ...overrides,
})

const REGISTRY: SourceRow[] = [
  row({
    code: 'ema_hmpc',
    name: 'EMA HMPC monographs',
    licence: 'Reproduction authorised with source acknowledgement (to verify)',
    access_method: 'pdf',
    latest_retrieved_at: '2026-11-02T12:35:17Z',
    latest_source_version: 'EMA/HMPC/321097/2012',
  }),
  row({
    code: 'fda_cyp_table',
    name: 'FDA enzyme and transporter table',
    licence: 'U.S. government work (public domain, to verify page notices)',
    redistributable: true,
  }),
  row({
    code: 'livertox',
    name: 'LiverTox',
    licence: 'Copyright free (NIDDK); acknowledgement requested.',
    licence_status: 'verified',
    redistributable: true,
  }),
  row({
    code: 'rxnav',
    name: 'RxNorm / RxNav',
    licence: 'Free from NLM',
    licence_status: 'catalogue',
  }),
  row({
    code: 'supp_ai',
    name: 'Supp.AI',
    licence: 'AI2 Terms forbid redistribution without written permission',
  }),
  row({
    code: 'pubmed',
    name: 'PubMed',
    licence: 'Metadata free; abstracts publisher-copyrighted (local store only)',
  }),
  row({ code: 'ddid', name: 'DDID', licence: 'Not stated in the downloaded files' }),
  row({ code: 'nih_dsld', name: 'NIH DSLD product labels', licence: 'Not in download' }),
]

describe('sources and methodology', () => {
  async function renderSources() {
    mockFetch({ ...BASE_ROUTES, '/api/v1/sources': [200, REGISTRY] })
    renderWithProviders(<AppRoutes />, { route: '/sources' })
    await screen.findByRole('region', { name: 'Regulatory & government evidence' })
  }

  it('groups the registry by category and keeps manufacturer labels apart', async () => {
    await renderSources()
    const regulatory = screen.getByRole('region', { name: 'Regulatory & government evidence' })
    expect(within(regulatory).getByText('EMA HMPC monographs')).toBeInTheDocument()
    expect(within(regulatory).getByText('Herbal monographs')).toBeInTheDocument()
    expect(within(regulatory).queryByText('NIH DSLD product labels')).not.toBeInTheDocument()

    const manufacturer = screen.getByRole('region', {
      name: 'Manufacturer product-label information',
    })
    expect(within(manufacturer).getByText('NIH DSLD product labels')).toBeInTheDocument()
    expect(
      within(manufacturer).getAllByText(/Manufacturer label information — not clinical evidence/)
        .length,
    ).toBeGreaterThan(0)

    // The registry is not turned into study counts or database administration details.
    expect(screen.queryByText(/\d[\d,]* records/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Last run/i)).not.toBeInTheDocument()
  })

  it('does not repeat the licence status on every source card', async () => {
    await renderSources()
    const cards = [
      screen.getByRole('region', { name: 'Regulatory & government evidence' }),
      screen.getByRole('region', { name: 'Supplementary research material' }),
      screen.getByRole('region', { name: 'Manufacturer product-label information' }),
    ]
    for (const card of cards) {
      expect(within(card).queryByText('Licence unverified')).not.toBeInTheDocument()
      expect(within(card).queryByText('Licence verified')).not.toBeInTheDocument()
    }
    // One compact, labelled entry point per source instead.
    expect(
      screen.getByRole('button', {
        name: 'Licence details for EMA HMPC monographs: Licence unverified',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Licence details for LiverTox: Licence verified' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Licence details for RxNorm / RxNav: Catalogue licence' }),
    ).toBeInTheDocument()
  })

  it('opens licence details for an unverified source without upgrading it, and returns focus on Escape', async () => {
    const user = userEvent.setup()
    await renderSources()
    const trigger = screen.getByRole('button', {
      name: 'Licence details for EMA HMPC monographs: Licence unverified',
    })
    await user.click(trigger)

    const dialog = screen.getByRole('dialog', { name: 'EMA HMPC monographs' })
    expect(within(dialog).getByText('Licence unverified')).toBeInTheDocument()
    expect(within(dialog).queryByText('Licence verified')).not.toBeInTheDocument()
    expect(
      within(dialog).getByText('Reproduction authorised with source acknowledgement (to verify)'),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(/does not treat EMA content as freely redistributable/),
    ).toBeInTheDocument()
    expect(within(dialog).getByText(/Not redistributable\./)).toBeInTheDocument()
    expect(
      within(dialog).getByText('Acknowledgement of the source is part of the recorded qualification.'),
    ).toBeInTheDocument()
    // Unrecorded metadata is stated as unrecorded, never filled in.
    expect(within(dialog).getByText('No licence URL is recorded.')).toBeInTheDocument()
    expect(within(dialog).getByText('PDF documents')).toBeInTheDocument()
    expect(within(dialog).getByText(/EMA\/HMPC\/321097\/2012/)).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: /example\.org\/ema_hmpc/ })).toHaveAttribute(
      'href',
      'https://example.org/ema_hmpc',
    )
    expect(document.body.style.overflow).toBe('hidden')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('traps focus inside the dialog and closes from the close button', async () => {
    const user = userEvent.setup()
    await renderSources()
    await user.click(
      screen.getByRole('button', { name: 'Licence details for LiverTox: Licence verified' }),
    )
    const dialog = screen.getByRole('dialog', { name: 'LiverTox' })
    const close = within(dialog).getByRole('button', { name: 'Close licence details' })
    expect(close).toHaveFocus()
    await user.tab()
    // Focus stays inside the dialog, never on the page behind it.
    expect(dialog.contains(document.activeElement)).toBe(true)
    await user.tab({ shift: true })
    expect(dialog.contains(document.activeElement)).toBe(true)
    await user.click(close)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it.each([
    [
      'LiverTox',
      'Licence verified',
      [/Verified: copyright free \(NIDDK\)/, 'Acknowledgement of NIDDK / LiverTox is requested.'],
    ],
    [
      'RxNorm / RxNav',
      'Catalogue licence',
      [/not a verified licence/, /ATC codes are owned by the WHO Collaborating Centre/],
    ],
    [
      'Supp.AI',
      'Licence unverified',
      [
        /forbid redistribution without written permission/,
        /not permission to reuse or redistribute it/,
        /Permission required\./,
      ],
    ],
    [
      'PubMed',
      'Licence unverified',
      [
        /Abstracts are copyrighted by their publishers/,
        /local store only/,
        /Restricted: local store only\./,
      ],
    ],
    [
      'DDID',
      'Licence unverified',
      [/have not been verified/, /No redistribution permission is implied\./],
    ],
    [
      'FDA enzyme and transporter table',
      'Licence unverified',
      [/page notices still need to be verified/, /Recorded as redistributable, not confirmed\./],
    ],
    [
      'NIH DSLD product labels',
      'Licence unverified',
      [
        'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
        /not used for A–E classification/,
        /Not redistributable\./,
      ],
    ],
  ])('keeps the recorded restrictions for %s', async (name, status, expected) => {
    const user = userEvent.setup()
    await renderSources()
    await user.click(screen.getByRole('button', { name: `Licence details for ${name}: ${status}` }))
    const dialog = screen.getByRole('dialog', { name })
    expect(within(dialog).getAllByText(status).length).toBeGreaterThan(0)
    for (const text of expected) {
      expect(within(dialog).getAllByText(text).length).toBeGreaterThan(0)
    }
  })

  it('presents each source once, with the licence terms explained at the bottom', async () => {
    await renderSources()
    // No second, tabular presentation of the same sources.
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText('Licence overview')).not.toBeInTheDocument()
    // Exactly one licence-details entry point per registered source.
    expect(screen.getAllByRole('button', { name: /^Licence details for / })).toHaveLength(
      REGISTRY.length,
    )
    for (const source of REGISTRY) {
      expect(
        screen
          .getAllByRole('heading', { level: 4 })
          .filter((heading) => heading.textContent?.startsWith(source.name)),
      ).toHaveLength(1)
    }

    const terms = screen.getByRole('heading', { name: 'How licences are recorded' })
    for (const term of [
      'Licence verified',
      'Catalogue licence',
      'Licence unverified',
      'Redistributable',
      'Not redistributable',
      'Restricted or permission required',
    ]) {
      expect(screen.getAllByText(term).length).toBeGreaterThan(0)
    }
    // The explanation comes after the registry, not before it.
    const registry = screen.getByRole('heading', { name: 'Registered sources' })
    expect(
      registry.compareDocumentPosition(terms) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('reports an unavailable registry without a source list', async () => {
    mockFetch({
      ...BASE_ROUTES,
      '/api/v1/sources': [503, { error: { code: 'service_unavailable', message: 'down' } }],
    })
    renderWithProviders(<AppRoutes />, { route: '/sources' })
    expect(await screen.findByText(/source registry could not be loaded/i)).toBeInTheDocument()
  })
})
