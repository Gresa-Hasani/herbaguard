import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import { ASK_INSUFFICIENT, ASK_RESPONSE, ASK_WITH_LABEL, META } from './fixtures'
import type { AskResponse } from '../lib/types'
import { mockFetch, renderWithProviders } from './render'

const BASE_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
}

/** The user-facing answer never shows pipeline timing, retrieval mode or cache history. */
function expectNoPipelineTiming() {
  expect(screen.queryByText('Pipeline timing')).not.toBeInTheDocument()
  for (const name of [
    'question_understanding_ms',
    'retrieval_ms',
    'context_assembly_ms',
    'llm_generation_ms',
    'validation_ms',
    'total_response_ms',
  ]) {
    expect(screen.queryByText(name)).not.toBeInTheDocument()
  }
  expect(screen.queryByText('Not exposed')).not.toBeInTheDocument()
  expect(screen.queryByText('Not run')).not.toBeInTheDocument()
  expect(screen.queryByText(/Retrieval mode/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/Browser round-trip/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/\d+s elapsed/)).not.toBeInTheDocument()
  expect(screen.queryByText(/originally took/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/No language model ran/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/prepared earlier/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/Retrieval and generation details/i)).not.toBeInTheDocument()
}

async function ask(question: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Your question'), question)
  await user.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('evidence assistant', () => {
  it('shows a real answer with citations, limitations and only reported pipeline timings', async () => {
    let postedBody: unknown = null
    let resolveRequest: ((value: [number, unknown]) => void) | null = null
    const pending = new Promise<[number, unknown]>((resolve) => {
      resolveRequest = resolve
    })
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': ({ body }) => {
        postedBody = body
        return pending
      },
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })

    await ask('What does the evidence say about St John’s wort and warfarin?')
    expect(
      await screen.findByText('Retrieving evidence and validating an answer…'),
    ).toBeInTheDocument()
    // A prepared answer returns within seconds: the long-wait explanation is not shown at 0 s.
    expect(screen.queryByText(/can take several minutes/i)).not.toBeInTheDocument()

    await act(async () => {
      resolveRequest?.([200, ASK_RESPONSE])
      await pending
    })

    expect(await screen.findByRole('heading', { name: 'Answer', level: 2 })).toBeInTheDocument()
    expect((await screen.findAllByText(/EMA guidance states/i)).length).toBeGreaterThan(0)
    expect(screen.getByText('Answered from cited evidence')).toBeInTheDocument()
    expect(screen.getByText('Limitations and uncertainty')).toBeInTheDocument()
    expect(
      screen.getByText(/The answer is limited to the retrieved sources/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/Resolved entities:/)).toBeInTheDocument()
    expect(screen.getByText('Documented')).toBeInTheDocument()

    const citations = screen.getByRole('region', { name: 'Citations' })
    expect(within(citations).getByText('S1')).toBeInTheDocument()
    expect(within(citations).getByText('C1')).toBeInTheDocument()
    expect(
      within(citations).getByText(/Concomitant use of St John’s wort and warfarin is not recommended/i),
    ).toBeInTheDocument()
    expect(
      within(citations).getByText(/Direct evidence/i),
    ).toBeInTheDocument()

    expectNoPipelineTiming()

    expect(postedBody).toEqual({
      question: 'What does the evidence say about St John’s wort and warfarin?',
      allow_remote_drug_lookup: false,
    })
  })

  it('keeps NIH DSLD citations in a separately warned section', async () => {
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': [200, ASK_WITH_LABEL],
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })

    await ask('What does the evidence say about St John’s wort and warfarin?')
    const labels = await screen.findByRole('region', { name: 'Product labels (NIH DSLD)' })
    expect(
      within(labels).getByRole('heading', { name: 'Product labels (NIH DSLD)' }),
    ).toBeInTheDocument()
    expect(
      within(labels).getAllByText(
        'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
      ).length,
    ).toBeGreaterThanOrEqual(2)
    expect(
      within(labels).getByText(/Consult your physician if you take anticoagulants/i),
    ).toBeInTheDocument()

    const clinical = screen.getByRole('region', { name: 'Citations' })
    expect(within(clinical).queryByText(/Consult your physician/i)).not.toBeInTheDocument()
  })

  it('shows insufficient evidence without fabricating an answer', async () => {
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': [200, ASK_INSUFFICIENT],
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })

    await ask('Is an unlisted herb safe with an unlisted drug?')

    expect(
      await screen.findByText('The evidence was insufficient to answer'),
    ).toBeInTheDocument()
    expect(screen.getByText(/No answer is being inferred/i)).toBeInTheDocument()
    expect(screen.queryByText(/EMA guidance states/i)).not.toBeInTheDocument()
    expect(screen.getByText('No clinical citations were returned')).toBeInTheDocument()
  })

  it('shows a request failure and no answer text', async () => {
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': [
        500,
        {
          error: {
            code: 'assistant_failed',
            message: 'The assistant could not complete the request',
            request_id: 'req-ask',
          },
        },
      ],
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })

    await ask('What does the evidence say about ginkgo?')

    expect(
      await screen.findByText('The assistant could not complete the request'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Request ID: req-ask/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Answer', level: 2 })).not.toBeInTheDocument()
    expect(screen.getByText(/Do not treat this as evidence/i)).toBeInTheDocument()
  })

  it('shows a cached answer exactly like a normal one, without presenting old timings as its own', async () => {
    const cached: AskResponse = {
      ...ASK_RESPONSE,
      generation: { ...ASK_RESPONSE.generation, duration_ms: 0 },
      cache: {
        served_from_cache: true,
        generated_at: '2026-11-08T09:00:00Z',
        original_generation_ms: 214297,
        validation_status: 'passed',
      },
    }
    mockFetch({ ...BASE_ROUTES, 'POST /api/v1/ai/ask': [200, cached] })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })

    await ask('What does the evidence say about St John’s wort and warfarin?')

    // same presentation as a normal answer
    expect(await screen.findByRole('heading', { name: 'Answer', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('Answered from cited evidence')).toBeInTheDocument()
    expect((await screen.findAllByText(/EMA guidance states/i)).length).toBeGreaterThan(0)
    const citations = screen.getByRole('region', { name: 'Citations' })
    expect(within(citations).getByText('S1')).toBeInTheDocument()
    expect(screen.getByText('Limitations and uncertainty')).toBeInTheDocument()
    expect(screen.queryByText(/can take several minutes/i)).not.toBeInTheDocument()

    // identical, clean presentation: nothing about timing or where the answer came from
    expectNoPipelineTiming()
  })
})
