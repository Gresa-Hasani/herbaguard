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
const DEFAULT_TIMEOUT_MS = 30_000

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

interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: externalSignal, ...init } = options
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const forwardAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', forwardAbort)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch {
    if (timedOut) {
      throw new ApiError(0, {
        code: 'timeout',
        message: 'The request took too long. Please try again.',
      })
    }
    if (controller.signal.aborted) {
      throw new ApiError(0, { code: 'cancelled', message: 'The request was cancelled.' })
    }
    throw new ApiError(0, {
      code: 'network_error',
      message: 'The HerbaGuard service could not be reached.',
    })
  } finally {
    clearTimeout(timer)
    externalSignal?.removeEventListener('abort', forwardAbort)
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

export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'GET' })
}

export function apiPost<T>(path: string, body: unknown, options?: RequestOptions): Promise<T> {
  return request<T>(path, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    body: JSON.stringify(body),
  })
}
