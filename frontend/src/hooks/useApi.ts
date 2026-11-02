import { useQuery } from '@tanstack/react-query'

import { apiGet } from '../lib/api'
import type { MetaResponse, ReadinessResponse } from '../lib/types'

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiGet<MetaResponse>('/api/v1/meta'),
    staleTime: Infinity,
  })
}

export function useReadiness() {
  return useQuery({
    queryKey: ['health', 'ready'],
    // A 503 from the readiness probe still carries a useful body, so it is not treated as fatal.
    queryFn: () => apiGet<ReadinessResponse>('/api/v1/health/ready'),
    refetchInterval: 30_000,
    retry: false,
  })
}
