import { useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from '../lib/api'
import { askTimeoutMs } from '../lib/ask'
import type {
  AskResponse,
  CoverageRow,
  Drug,
  EvidenceSummary,
  InteractionCheckResponse,
  MetaResponse,
  Page,
  PlantCoverage,
  ProductLabel,
  ReadinessResponse,
  SourceRow,
  TaxonDetail,
  TaxonSummary,
} from '../lib/types'

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

export function usePlantSearch(query: string, enabled = true) {
  const q = query.trim()
  return useQuery({
    queryKey: ['plants', 'search', q],
    queryFn: () =>
      apiGet<Page<TaxonSummary>>(`/api/v1/plants?q=${encodeURIComponent(q)}&limit=10`),
    enabled: enabled && q.length >= 2,
    staleTime: 60_000,
  })
}

export const PLANT_PAGE_SIZE = 24

/**
 * The plant index, paged from the server (`limit`/`offset`), optionally filtered by a name query
 * (scientific, common, synonym or pharmaceutical name). Without a query it lists every taxon.
 */
export function usePlantCatalog(query: string) {
  const q = query.trim()
  return useInfiniteQuery({
    queryKey: ['plants', 'catalog', q],
    queryFn: ({ pageParam }) =>
      apiGet<Page<TaxonSummary>>(
        `/api/v1/plants?limit=${PLANT_PAGE_SIZE}&offset=${pageParam}${
          q ? `&q=${encodeURIComponent(q)}` : ''
        }`,
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const loaded = last.offset + last.items.length
      return last.items.length > 0 && loaded < last.total ? loaded : undefined
    },
    enabled: q.length === 0 || q.length >= 2,
    staleTime: 60_000,
  })
}

/** Per-taxon coverage by kind of material (taxonomy, regulatory, literature, labels). */
export function usePlantCoverage() {
  return useQuery({
    queryKey: ['coverage', 'plants'],
    queryFn: () => apiGet<PlantCoverage>('/api/v1/coverage/plants'),
    staleTime: 60_000,
    retry: false,
  })
}

export function usePlantDetail(wfoId: string | null) {
  return useQuery({
    queryKey: ['plant', wfoId],
    queryFn: () => apiGet<TaxonDetail>(`/api/v1/plants/${encodeURIComponent(wfoId ?? '')}`),
    enabled: Boolean(wfoId),
    staleTime: 60_000,
  })
}

export function usePlantEvidence(wfoId: string | null, limit = 50) {
  return useQuery({
    queryKey: ['plant', wfoId, 'evidence', limit],
    queryFn: () =>
      apiGet<Page<EvidenceSummary>>(
        `/api/v1/evidence?wfo_id=${encodeURIComponent(wfoId ?? '')}&limit=${limit}`,
      ),
    enabled: Boolean(wfoId),
    staleTime: 60_000,
  })
}

export function useProductLabels(wfoId: string | null) {
  return useQuery({
    queryKey: ['plant', wfoId, 'product-labels'],
    queryFn: () =>
      apiGet<Page<ProductLabel>>(
        `/api/v1/plants/${encodeURIComponent(wfoId ?? '')}/product-labels?limit=20`,
      ),
    enabled: Boolean(wfoId),
    staleTime: 60_000,
  })
}

export function useDrugSearch(query: string) {
  const q = query.trim()
  return useQuery({
    queryKey: ['drugs', 'search', q],
    queryFn: () => apiGet<Page<Drug>>(`/api/v1/drugs?q=${encodeURIComponent(q)}&limit=10`),
    enabled: q.length >= 2,
    staleTime: 60_000,
  })
}

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: () => apiGet<SourceRow[]>('/api/v1/sources'),
    staleTime: 60_000,
  })
}

export function useCoverage() {
  return useQuery({
    queryKey: ['coverage'],
    queryFn: () => apiGet<CoverageRow[]>('/api/v1/coverage'),
    staleTime: 60_000,
  })
}

export interface InteractionCheckInput {
  herb: string
  drugs: string[]
}

export function useInteractionCheck() {
  return useMutation({
    mutationFn: (input: InteractionCheckInput) =>
      apiPost<InteractionCheckResponse>('/api/v1/interactions/check', {
        herb: input.herb,
        drugs: input.drugs,
        // The UI only offers drugs from the HerbaGuard index; no external RxNav lookup.
        allow_remote_drug_lookup: false,
      }),
  })
}

export interface AskInput {
  question: string
  /** Lets the page cancel the in-flight request. */
  signal?: AbortSignal
}

export function useAsk() {
  return useMutation({
    mutationFn: ({ question, signal }: AskInput) =>
      apiPost<AskResponse>(
        '/api/v1/ai/ask',
        { question, allow_remote_drug_lookup: false },
        // Aligned with the backend's worst case (see lib/ask.ts); not an arbitrary large value.
        { timeoutMs: askTimeoutMs(), signal },
      ),
    // A failed generation is never retried silently: the user decides, because each attempt is a
    // multi-minute CPU job.
    retry: false,
  })
}
