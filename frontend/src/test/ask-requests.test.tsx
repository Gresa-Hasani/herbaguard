import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'
import { ApiError } from '../lib/api'
import { DEFAULT_ASK_TIMEOUT_MS, askTimeoutMs, describeAskFailure } from '../lib/ask'
import { ASK_RESPONSE, META } from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const BASE_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
}
const QUESTION = 'What does the evidence say about St John’s wort and warfarin?'

function typeQuestion(text = QUESTION) {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: text } })
}

function envelope(status: number, code: string, message: string, details?: unknown) {
  return [status, { error: { code, message, details, request_id: 'req-1' } }] as [number, unknown]
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('ask timeout policy', () => {
  it('waits longer than the 120 s that used to cut off legitimate backend answers', () => {
    // Measured on the CPU-only dev machine: 118.9 s warm, 227.5 s with a cold model.
    expect(DEFAULT_ASK_TIMEOUT_MS).toBeGreaterThan(227_500)
    // Backend worst case: 2 attempts x 240 s, plus a margin for retrieval and validation.
    expect(DEFAULT_ASK_TIMEOUT_MS).toBeGreaterThanOrEqual(2 * 240_000)
    expect(askTimeoutMs()).toBe(DEFAULT_ASK_TIMEOUT_MS)
  })

  it('can be configured and ignores unusable values', () => {
    vi.stubEnv('VITE_ASK_TIMEOUT_MS', '300000')
    expect(askTimeoutMs()).toBe(300_000)
    vi.stubEnv('VITE_ASK_TIMEOUT_MS', 'soon')
    expect(askTimeoutMs()).toBe(DEFAULT_ASK_TIMEOUT_MS)
    vi.stubEnv('VITE_ASK_TIMEOUT_MS', '50')
    expect(askTimeoutMs()).toBe(DEFAULT_ASK_TIMEOUT_MS)
  })
})

describe('describeAskFailure', () => {
  const failure = (error: ApiError) => describeAskFailure(error, 540)

  it('tells a browser timeout apart from backend failures', () => {
    const client = failure(new ApiError(0, { code: 'timeout', message: 'x' }))
    expect(client.kind).toBe('client_timeout')
    expect(client.message).toMatch(/no answer was received/i)

    const generator = failure(
      new ApiError(503, {
        code: 'service_unavailable',
        message: 'The answer generator is not available: The provider did not answer in time.',
        details: { provider: 'ollama', kind: 'timeout' },
      }),
    )
    expect(generator.kind).toBe('generator_timeout')

    const model = failure(
      new ApiError(503, {
        code: 'service_unavailable',
        message: 'The answer generator is not available: The provider could not be reached.',
        details: { provider: 'ollama', kind: 'unavailable' },
      }),
    )
    expect(model.kind).toBe('model_unavailable')
    expect(model.message).toMatch(/could not be reached/)

    expect(failure(new ApiError(429, { code: 'too_many_requests', message: 'busy' })).kind).toBe(
      'busy',
    )
    expect(failure(new ApiError(500, { code: 'internal_error', message: 'boom' })).kind).toBe(
      'backend_error',
    )
    expect(failure(new ApiError(0, { code: 'network_error', message: 'x' })).kind).toBe(
      'unreachable',
    )
    expect(failure(new ApiError(0, { code: 'cancelled', message: 'x' })).kind).toBe('cancelled')
  })

  it('does not offer a retry for an ambiguous entity', () => {
    const ambiguous = failure(new ApiError(409, { code: 'ambiguous_entity', message: 'ginseng?' }))
    expect(ambiguous.kind).toBe('ambiguous')
    expect(ambiguous.retryable).toBe(false)
  })
})

describe('assistant request handling', () => {
  it('sends one request even when Ask is activated twice before the first render', async () => {
    const fetchSpy = mockFetch({ ...BASE_ROUTES, 'POST /api/v1/ai/ask': 'hang' })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    typeQuestion()

    const form = screen.getByLabelText('Your question').closest('form') as HTMLFormElement
    fireEvent.submit(form)
    fireEvent.submit(form)

    await screen.findByText('Retrieving evidence and validating an answer…')
    const asks = fetchSpy.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(asks).toHaveLength(1)
  })

  it('cancels a pending request, keeps the question and retries on demand', async () => {
    let calls = 0
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': ({ signal }) => {
        calls += 1
        if (calls === 1) {
          return new Promise((_resolve, reject) => {
            signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          })
        }
        return [200, ASK_RESPONSE]
      },
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    typeQuestion()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel request' }))
    expect(await screen.findByText('Request cancelled')).toBeInTheDocument()
    expect(screen.getByLabelText('Your question')).toHaveValue(QUESTION)
    expect(screen.queryByRole('heading', { name: 'Answer', level: 2 })).not.toBeInTheDocument()
    expect(screen.getByText(/Do not treat this as evidence/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry question' }))
    expect(await screen.findByRole('heading', { name: 'Answer', level: 2 })).toBeInTheDocument()
    expect(calls).toBe(2)
  })

  it('keeps waiting past 120 s and only reports a browser timeout at the aligned limit', async () => {
    vi.useFakeTimers()
    mockFetch({ ...BASE_ROUTES, 'POST /api/v1/ai/ask': 'hang' })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    typeQuestion()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(130_000)
    })
    expect(screen.queryByText('The browser stopped waiting')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel request' })).toBeInTheDocument()
    // no elapsed-time counter is shown, only the cancel control and the wait explanation
    expect(screen.queryByText(/elapsed/i)).not.toBeInTheDocument()
    // after a real wait, the long-generation explanation appears
    expect(screen.getByText(/can take several minutes/i)).toBeInTheDocument()
    expect(screen.getByText(/No partial or fabricated text is shown/i)).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEFAULT_ASK_TIMEOUT_MS)
    })
    expect(screen.getByText('The browser stopped waiting')).toBeInTheDocument()
    expect(screen.getByLabelText('Your question')).toHaveValue(QUESTION)
    expect(screen.getByRole('button', { name: 'Retry question' })).toBeEnabled()
    expect(screen.queryByRole('heading', { name: 'Answer', level: 2 })).not.toBeInTheDocument()
  })

  it('shows an unavailable model as its own state, without an answer', async () => {
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': envelope(
        503,
        'service_unavailable',
        'The answer generator is not available: The provider could not be reached.',
        { provider: 'ollama', kind: 'unavailable' },
      ),
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    typeQuestion()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByText('The answer generator is not available')).toBeInTheDocument()
    expect(screen.getByText(/could not be reached/)).toBeInTheDocument()
    expect(screen.getByText(/Request ID: req-1/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Answer', level: 2 })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry question' })).toBeEnabled())
  })

  it('shows a backend generator timeout as different from a browser timeout', async () => {
    mockFetch({
      ...BASE_ROUTES,
      'POST /api/v1/ai/ask': envelope(
        503,
        'service_unavailable',
        'The answer generator is not available: The provider did not answer in time.',
        { provider: 'ollama', kind: 'timeout' },
      ),
    })
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    typeQuestion()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(
      await screen.findByText('The language model did not finish in time'),
    ).toBeInTheDocument()
    expect(screen.queryByText('The browser stopped waiting')).not.toBeInTheDocument()
  })
})
