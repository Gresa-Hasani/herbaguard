/** Types mirroring backend schemas (herbaguard.api.schemas). */

export interface MetaResponse {
  name: string
  version: string
  environment: string
  api_version: string
  disclaimer: string
}

export interface ReadinessCheck {
  name: string
  status: 'ok' | 'error'
  detail: string | null
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded'
  checks: ReadinessCheck[]
}
