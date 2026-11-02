import { describe, expect, it } from 'vitest'

import { ApiError, apiGet } from '../lib/api'
import { mockFetch } from './render'

describe('apiGet', () => {
  it('returns the parsed body on success', async () => {
    mockFetch({ '/api/v1/health': [200, { status: 'ok' }] })
    await expect(apiGet('/api/v1/health')).resolves.toEqual({ status: 'ok' })
  })

  it('maps the backend error envelope to ApiError', async () => {
    mockFetch({
      '/api/v1/plants': [
        409,
        {
          error: {
            code: 'ambiguous_entity',
            message: "Several taxa match 'ginseng'.",
            details: { candidates: ['wfo-0000263606', 'wfo-0000948117'] },
            request_id: 'abc',
          },
        },
      ],
    })
    const error = await apiGet('/api/v1/plants').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: 'ambiguous_entity',
      requestId: 'abc',
      message: "Several taxa match 'ginseng'.",
    })
  })

  it('reports non-envelope errors and network failures distinctly', async () => {
    mockFetch({ '/api/v1/broken': [502, 'Bad Gateway'] })
    await expect(apiGet('/api/v1/broken')).rejects.toMatchObject({
      status: 502,
      code: 'unexpected_response',
    })
    await expect(apiGet('/api/v1/unreachable')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
    })
  })
})
