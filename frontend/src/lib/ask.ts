/**
 * Evidence Assistant request policy: how long the browser waits, and how failures are described.
 *
 * Timeout layers (all must be compatible; see docs/ai/request-timeouts.md):
 *   browser (this file)  >=  dev proxy / nginx  >=  backend worst case
 *   backend worst case = (1 + llm_max_regenerations) x llm_timeout_seconds + retrieval
 *                      = 2 x 240 s + a few seconds
 * The browser waits for that worst case plus a margin so it never abandons a request the backend
 * is still legitimately working on. The user can cancel at any time.
 */
import { ApiError } from './api'

const BACKEND_ATTEMPT_SECONDS = 240 // HERBAGUARD_LLM_TIMEOUT_SECONDS default
const BACKEND_ATTEMPTS = 2 // one generation + HERBAGUARD_LLM_MAX_REGENERATIONS (default 1)
const MARGIN_SECONDS = 60 // retrieval, validation, serialisation, proxy hops

export const DEFAULT_ASK_TIMEOUT_MS =
  (BACKEND_ATTEMPT_SECONDS * BACKEND_ATTEMPTS + MARGIN_SECONDS) * 1000

/** Browser-side wait for /ai/ask. Override with VITE_ASK_TIMEOUT_MS when the backend limits change. */
export function askTimeoutMs(): number {
  const configured = Number(import.meta.env.VITE_ASK_TIMEOUT_MS)
  return Number.isFinite(configured) && configured >= 10_000 ? configured : DEFAULT_ASK_TIMEOUT_MS
}

export type AskFailureKind =
  | 'client_timeout'
  | 'cancelled'
  | 'unreachable'
  | 'generator_timeout'
  | 'model_unavailable'
  | 'busy'
  | 'ambiguous'
  | 'backend_error'

export interface AskFailure {
  kind: AskFailureKind
  title: string
  message: string
  retryable: boolean
  requestId: string | null
}

const MODEL_UNAVAILABLE_KINDS = new Set([
  'unavailable',
  'model_not_found',
  'not_configured',
  'authentication',
])

/** Turns a failed request into one of the distinct states the Assistant page explains. */
export function describeAskFailure(error: unknown, timeoutSeconds: number): AskFailure {
  if (!(error instanceof ApiError)) {
    return {
      kind: 'backend_error',
      title: 'The assistant request failed',
      message: 'An unexpected error occurred before an answer was received.',
      retryable: true,
      requestId: null,
    }
  }
  const requestId = error.requestId
  const detailKind =
    typeof error.details === 'object' && error.details !== null && 'kind' in error.details
      ? String((error.details as { kind: unknown }).kind)
      : null

  if (error.code === 'timeout') {
    return {
      kind: 'client_timeout',
      title: 'The browser stopped waiting',
      message: `No response arrived within ${Math.round(timeoutSeconds / 60)} minutes, so this page gave up. The server may still have been working; no answer was received.`,
      retryable: true,
      requestId,
    }
  }
  if (error.code === 'cancelled') {
    return {
      kind: 'cancelled',
      title: 'Request cancelled',
      message: 'You cancelled the request. No answer was received.',
      retryable: true,
      requestId,
    }
  }
  if (error.code === 'network_error') {
    return {
      kind: 'unreachable',
      title: 'The HerbaGuard service could not be reached',
      message: 'The browser could not connect to the API. Check that the backend is running.',
      retryable: true,
      requestId,
    }
  }
  if (error.status === 503 && detailKind === 'timeout') {
    return {
      kind: 'generator_timeout',
      title: 'The language model did not finish in time',
      message:
        'The backend stopped waiting for the local language model. This is a server-side time limit, not a validation result.',
      retryable: true,
      requestId,
    }
  }
  if (error.status === 503 && (detailKind === null || MODEL_UNAVAILABLE_KINDS.has(detailKind))) {
    return {
      kind: 'model_unavailable',
      title: 'The answer generator is not available',
      message: error.message,
      retryable: true,
      requestId,
    }
  }
  if (error.status === 429) {
    return {
      kind: 'busy',
      title: 'The assistant is busy',
      message: 'Other questions are already being processed. Wait for them to finish and retry.',
      retryable: true,
      requestId,
    }
  }
  if (error.status === 409) {
    return {
      kind: 'ambiguous',
      title: 'The question names an ambiguous herb or drug',
      message: error.message,
      retryable: false,
      requestId,
    }
  }
  return {
    kind: 'backend_error',
    title: 'The assistant did not answer',
    message: error.message,
    retryable: true,
    requestId,
  }
}
