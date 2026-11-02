/**
 * Minimal typed client for the HerbaGuard API.
 *
 * Every non-2xx response is converted into an ApiError carrying the backend's standard
 * error envelope ({ error: { code, message, details, request_id } }).
 */

export interface ApiErrorBody {
  code: string
  message: string
  details?: unknown
  request_id?: string | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
    this.requestId = body.request_id ?? null
  }
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as ApiErrorBody).code === 'string' &&
    typeof (error as ApiErrorBody).message === 'string'
  )
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, {
      code: 'network_error',
      message: 'The HerbaGuard service could not be reached.',
    })
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorEnvelope(payload)) throw new ApiError(response.status, payload.error)
    throw new ApiError(response.status, {
      code: 'unexpected_response',
      message: `Unexpected response from the server (HTTP ${response.status}).`,
    })
  }
  return payload as T
}
