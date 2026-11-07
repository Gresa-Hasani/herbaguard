import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import type { Page, Drug } from '../lib/types'
import {
  INTERACTION_NO_EVIDENCE,
  INTERACTION_RESPONSE,
  META,
  TAXON_PAGE,
} from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const DRUG: Drug = {
  rxcui: '202421',
  name: 'warfarin',
  atc_classes: [
    { code: 'B01AA', name: 'Vitamin K antagonists', level: 4, system: 'ATC' },
  ],
}

const DRUG_PAGE: Page<Drug> = { items: [DRUG], total: 1, limit: 10, offset: 0 }

const SEARCH_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
  '/api/v1/plants?q=st%20john&limit=10': [200, TAXON_PAGE] as [number, unknown],
  '/api/v1/drugs?q=warfarin&limit=10': [200, DRUG_PAGE] as [number, unknown],
}

async function selectPair(user: UserEvent) {
  const herbInput = screen.getByLabelText('Search medicinal herbs')
  await user.type(herbInput, 'st john')
  await user.click(await screen.findByRole('button', { name: /St John's wort/i }))

  const drugInput = screen.getByLabelText('Search medications')
  await user.type(drugInput, 'warfarin')
  await user.click(await screen.findByRole('button', { name: /warfarin RxCUI/i }))
}

describe('interaction checker', () => {
  it('searches real indexed herbs and drugs, posts the selected pair and renders the backend class', async () => {
    const user = userEvent.setup()
    let postedBody: unknown = null
    let resolveRequest: ((value: [number, unknown]) => void) | null = null
    const pending = new Promise<[number, unknown]>((resolve) => {
      resolveRequest = resolve
    })

    mockFetch({
      ...SEARCH_ROUTES,
      'POST /api/v1/interactions/check': ({ body }) => {
        postedBody = body
        return pending
      },
    })
    renderWithProviders(<AppRoutes />, { route: '/interactions' })

    expect(screen.getByRole('button', { name: 'Check interaction' })).toBeDisabled()
    await selectPair(user)
    expect(screen.getByText('Selected herb')).toBeInTheDocument()

    const submit = screen.getByRole('button', { name: 'Check interaction' })
    expect(submit).toBeEnabled()
    await user.click(submit)

    expect(await screen.findByText('Checking stored evidence…')).toBeInTheDocument()

    await act(async () => {
      resolveRequest?.([200, INTERACTION_RESPONSE])
      await pending
    })

    expect(
      await screen.findByRole('heading', { name: /Result for St John's wort/i }),
    ).toBeInTheDocument()

    expect(postedBody).toEqual({
      herb: 'Hyperici herba',
      drugs: ['warfarin'],
      allow_remote_drug_lookup: false,
    })

    const result = screen
      .getByRole('heading', { name: /Result for St John's wort/i })
      .closest('section') as HTMLElement
    expect(within(result).getByText('Documented')).toBeInTheDocument()
    expect(within(result).getByText('Interaction class')).toBeInTheDocument()
    expect(
      within(result).getByText(/An EMA monograph states that concomitant use/i),
    ).toBeInTheDocument()
    expect(within(result).getByText(/Source severity wording/i)).toBeInTheDocument()
    expect(within(result).getAllByText('“not recommended”').length).toBeGreaterThanOrEqual(2)
    expect(within(result).getByText(/Concomitant use is not recommended/i)).toBeInTheDocument()
    expect(
      within(result).getByRole('link', {
        name: /European Union herbal monograph on Hypericum perforatum/i,
      }),
    ).toHaveAttribute('href', 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba')
    expect(within(result).getByText(/Enzyme induction/i)).toBeInTheDocument()
    expect(screen.getByText(/round-trip \d+ ms/i)).toBeInTheDocument()
  })

  it('renders class D without implying safety and shows the empty decisive-statement state', async () => {
    const user = userEvent.setup()
    mockFetch({
      ...SEARCH_ROUTES,
      'POST /api/v1/interactions/check': [200, INTERACTION_NO_EVIDENCE],
    })
    renderWithProviders(<AppRoutes />, { route: '/interactions' })
    await selectPair(user)
    await user.click(screen.getByRole('button', { name: 'Check interaction' }))

    expect(
      await screen.findByText(/No interaction evidence is not evidence of safety/i),
    ).toBeInTheDocument()
    expect(screen.getAllByText('No interaction evidence found').length).toBeGreaterThan(0)
    expect(screen.getByText('No decisive statement')).toBeInTheDocument()
    expect(screen.getByText(/This is not evidence that the combination is safe/i)).toBeInTheDocument()
  })

  it('shows a backend error without displaying a result', async () => {
    const user = userEvent.setup()
    mockFetch({
      ...SEARCH_ROUTES,
      'POST /api/v1/interactions/check': [
        503,
        {
          error: {
            code: 'service_unavailable',
            message: 'Interaction store unavailable',
            request_id: 'req-123',
          },
        },
      ],
    })
    renderWithProviders(<AppRoutes />, { route: '/interactions' })
    await selectPair(user)
    await user.click(screen.getByRole('button', { name: 'Check interaction' }))

    expect(await screen.findByText('Interaction store unavailable')).toBeInTheDocument()
    expect(screen.getByText(/Request ID: req-123/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Result for/ })).not.toBeInTheDocument()
    expect(screen.getByText(/should be read as reassurance about the combination/i)).toBeInTheDocument()
  })

  it('reports an empty result set as unknown rather than safe', async () => {
    const user = userEvent.setup()
    mockFetch({
      ...SEARCH_ROUTES,
      'POST /api/v1/interactions/check': [200, { ...INTERACTION_RESPONSE, results: [] }],
    })
    renderWithProviders(<AppRoutes />, { route: '/interactions' })
    await selectPair(user)
    await user.click(screen.getByRole('button', { name: 'Check interaction' }))

    expect(await screen.findByText('No medication results returned')).toBeInTheDocument()
    expect(screen.getByText(/This is not evidence that the combination is safe/i)).toBeInTheDocument()
  })
})
