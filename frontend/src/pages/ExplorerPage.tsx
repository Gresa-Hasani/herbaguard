import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { BotanicalBranch, LeafOrnament } from '../components/BotanicalArt'
import { EvidenceTypeBadge } from '../components/EvidenceBadges'
import { Icon } from '../components/icons'
import { ProductLabelsPanel } from '../components/ProductLabelsPanel'
import { ProvenanceList } from '../components/ProvenanceList'
import {
  Alert,
  Badge,
  Button,
  Disclosure,
  EmptyState,
  ExternalLink,
  KeyValue,
  PageHeader,
  SectionHeading,
  Skeleton,
  Spinner,
} from '../components/ui'
import { CoverageChips, CoverageStrip, CoverageSummary } from '../components/PlantCoverage'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import {
  usePlantCatalog,
  usePlantCoverage,
  usePlantDetail,
  usePlantEvidence,
  useProductLabels,
} from '../hooks/useApi'
import { EVIDENCE_GROUPS, EVIDENCE_GROUP_ORDER, USE_CATEGORY_LABELS } from '../lib/constants'
import { evidenceGroup, formatDate, humanize, pluralize, sourceLabel } from '../lib/format'
import type { EvidenceGroupKey } from '../lib/constants'
import type { EvidenceSummary, TaxonCoverage, TaxonSummary } from '../lib/types'

const GROUP_DOT: Record<EvidenceGroupKey, string> = {
  regulatory: 'bg-ev-regulatory',
  human: 'bg-ev-clinical',
  laboratory: 'bg-ev-supplementary',
  other: 'bg-class-e',
}

function EvidenceItem({ item }: { item: EvidenceSummary }) {
  return (
    <li className="rounded-lg border border-line bg-surface p-3.5 transition-colors hover:border-line-strong">
      <p className="font-medium leading-snug text-ink">
        <ExternalLink href={item.url}>{item.title}</ExternalLink>
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <EvidenceTypeBadge info={item.evidence_type} />
        <span>{sourceLabel(item.source_code)}</span>
        <span>{item.external_id}</span>
        {item.document_date ? <span>{formatDate(item.document_date)}</span> : null}
        {item.publication_year ? <span>{item.publication_year}</span> : null}
      </div>
      {item.relations.length > 0 ? (
        <p className="mt-2 text-xs text-muted">Relations: {item.relations.join(', ')}</p>
      ) : null}
    </li>
  )
}

function PlantTile({
  taxon,
  coverage,
  onSelect,
}: {
  taxon: TaxonSummary
  coverage: TaxonCoverage | undefined
  onSelect: (id: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(taxon.wfo_id)}
      className="group relative h-full w-full overflow-hidden rounded-xl border border-line bg-surface p-5 text-left shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-forest-500/60 hover:shadow-lift"
    >
      <LeafOrnament className="absolute -right-4 -top-4 h-24 w-24 text-forest-600/10 transition-transform duration-500 group-hover:rotate-6 group-hover:scale-110" />
      <p className="relative text-[11px] font-semibold uppercase tracking-wider text-teal-700">
        {taxon.family ?? 'Family not stored'}
      </p>
      <p className="relative mt-1 font-display text-xl font-semibold italic leading-tight text-forest-950">
        {taxon.scientific_name}
      </p>
      {taxon.authorship ? (
        <p className="relative text-xs text-muted">{taxon.authorship}</p>
      ) : null}
      <p className="relative mt-3 text-sm text-ink-soft">
        {taxon.herbs
          .map((herb) => `${herb.common_name ?? herb.pharmaceutical_name} (${herb.plant_part})`)
          .join(' · ')}
      </p>
      {taxon.matched_name && taxon.matched_name.name_type !== 'accepted' ? (
        <p className="relative mt-1 text-xs text-muted">
          Matched {humanize(taxon.matched_name.name_type).toLowerCase()} name “
          {taxon.matched_name.name}”
        </p>
      ) : null}
      {coverage ? (
        <div className="relative mt-3">
          <CoverageChips row={coverage} />
        </div>
      ) : null}
      <span className="relative mt-4 inline-flex items-center gap-1 text-xs font-semibold text-forest-700">
        Open record
        <Icon
          name="arrow"
          className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-1"
        />
      </span>
    </button>
  )
}

export function ExplorerPage() {
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('wfo')
  const [query, setQuery] = useState('')
  const debounced = useDebouncedValue(query)

  const searching = query.trim().length >= 2
  const catalog = usePlantCatalog(searching ? debounced : '')
  const coverage = usePlantCoverage()
  const detail = usePlantDetail(selectedId)
  const evidence = usePlantEvidence(selectedId)
  const labels = useProductLabels(selectedId)

  function select(wfoId: string) {
    setParams({ wfo: wfoId })
    setQuery('')
  }

  const items = catalog.data?.pages.flatMap((page) => page.items) ?? []
  const total = catalog.data?.pages[0]?.total ?? 0
  const listPending = catalog.isPending || (searching && catalog.isFetching && items.length === 0)
  const listError = catalog.isError
  const coverageById = new Map(coverage.data?.items.map((row) => [row.wfo_id, row]))
  const selectedCoverage = selectedId ? coverageById.get(selectedId) : undefined
  // Several taxa sharing one common name are all kept; the user must choose by scientific name.
  const sharedCommonName =
    searching && items.filter((t) => t.matched_name?.name_type === 'common').length > 1
  // Keep the open record visible in the rail even when it is not on the loaded pages.
  const railItems: Pick<TaxonSummary, 'wfo_id' | 'scientific_name' | 'herbs'>[] = [
    ...(selectedId && detail.data && !searching && !items.some((t) => t.wfo_id === selectedId)
      ? [detail.data]
      : []),
    ...items,
  ]
  const loadMore = catalog.hasNextPage ? (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => void catalog.fetchNextPage()}
      disabled={catalog.isFetchingNextPage}
    >
      {catalog.isFetchingNextPage ? 'Loading…' : `Load more (${items.length} of ${total})`}
    </Button>
  ) : null

  const groupedEvidence = new Map<EvidenceGroupKey, EvidenceSummary[]>()
  for (const item of evidence.data?.items ?? []) {
    const key = evidenceGroup(item.evidence_type.code)
    groupedEvidence.set(key, [...(groupedEvidence.get(key) ?? []), item])
  }

  const firstGroup = EVIDENCE_GROUP_ORDER.find((key) => (groupedEvidence.get(key)?.length ?? 0) > 0)

  const searchBox = (
    <div>
      <label htmlFor="explorer-search" className="block text-sm font-semibold text-ink">
        Find a herb
      </label>
      <div className="relative mt-1.5">
        <Icon
          name="search"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        />
        <input
          id="explorer-search"
          type="search"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Common, scientific or pharmaceutical name"
          className="w-full rounded-lg border border-line-strong bg-surface py-2.5 pl-9 pr-3 text-sm text-ink shadow-soft transition-shadow placeholder:text-muted/70 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/15"
        />
      </div>
      <p className="mt-2 text-xs text-muted">
        {searching
          ? `${total} matching plant record(s)`
          : catalog.hasNextPage
            ? `Showing ${items.length} of ${total} supported plants`
            : `Showing all ${total} supported plants`}
      </p>
    </div>
  )

  return (
    <div className="space-y-8">
      <PageHeader icon="leaf" eyebrow="Curated plant records" title="Herb Explorer">
        <p>
          Taxonomy, regulatory monographs, indications and indexed evidence for supported medicinal
          plants. Each evidence item keeps its source and document type. Product labels appear in a
          separate section and are never clinical evidence.
        </p>
      </PageHeader>

      <div className={selectedId ? 'grid gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]' : ''}>
        {/* Finder: a full-width discovery view, or a compact rail beside a record. */}
        <aside
          aria-label="Plant finder"
          className={selectedId ? 'hidden lg:block' : 'space-y-6'}
        >
          <div
            className={
              selectedId
                ? 'sticky top-6 space-y-4 rounded-xl border border-line bg-surface p-4 shadow-soft'
                : 'relative overflow-hidden rounded-2xl border border-line bg-sage-100 p-6 sm:p-8'
            }
          >
            {!selectedId ? (
              <LeafOrnament className="pointer-events-none absolute -right-6 -top-8 h-56 w-56 text-forest-600/10" />
            ) : null}
            <div className={selectedId ? '' : 'relative max-w-xl'}>{searchBox}</div>

            {selectedId ? (
              <div className="scrollbar-thin max-h-[30rem] overflow-y-auto">
                {listPending ? (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-4/5" />
                  </div>
                ) : listError ? (
                  <p className="text-sm text-danger">The herb index is unavailable right now.</p>
                ) : railItems.length > 0 ? (
                  <>
                  <ul className="space-y-1">
                    {railItems.map((taxon) => {
                      const active = taxon.wfo_id === selectedId
                      return (
                        <li key={taxon.wfo_id}>
                          <button
                            type="button"
                            onClick={() => select(taxon.wfo_id)}
                            aria-current={active ? 'true' : undefined}
                            className={`w-full rounded-lg border-l-[3px] px-3 py-2 text-left text-sm transition-colors ${
                              active
                                ? 'border-forest-600 bg-forest-50 text-forest-950'
                                : 'border-transparent text-ink hover:bg-surface-2'
                            }`}
                          >
                            <span className="block font-medium italic">{taxon.scientific_name}</span>
                            <span className="block text-xs text-muted">
                              {taxon.herbs
                                .map((herb) => herb.common_name ?? herb.pharmaceutical_name)
                                .join(' · ')}
                            </span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                  {loadMore ? <div className="mt-3">{loadMore}</div> : null}
                  </>
                ) : (
                  <p className="text-sm text-muted">
                    No curated plant matches that name. Try a scientific or pharmaceutical name.
                  </p>
                )}
              </div>
            ) : null}
          </div>

          {!selectedId ? null : (
            <p className="rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-muted">
              Taxonomy follows the World Flora Online identifiers stored by the backend. A common
              name can map to more than one taxon; the record shows every stored match.
            </p>
          )}
        </aside>

        <div className="min-w-0">
          {!selectedId ? (
            <div className="space-y-5">
              {coverage.data && !searching ? <CoverageSummary rows={coverage.data.items} /> : null}
              <SectionHeading
                eyebrow={searching ? 'Search results' : 'Browse'}
                title={searching ? 'Matching plants' : 'Supported medicinal plants'}
                description="Select a record to see its regulatory information, evidence and product-label coverage."
              />
              {sharedCommonName ? (
                <Alert tone="info" title="This name matches more than one plant">
                  <p>
                    Common names can refer to different species. All stored matches are shown;
                    choose by scientific name rather than assuming one record.
                  </p>
                </Alert>
              ) : null}
              {listPending ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {[0, 1, 2, 3, 4, 5].map((n) => (
                    <Skeleton key={n} className="h-40 w-full" />
                  ))}
                </div>
              ) : listError ? (
                <EmptyState title="Plant records are unavailable" icon="alert">
                  <p>The curated herb index could not be loaded. Please try again.</p>
                </EmptyState>
              ) : items.length > 0 ? (
                <>
                  <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {items.map((taxon) => (
                      <li key={taxon.wfo_id}>
                        <PlantTile
                          taxon={taxon}
                          coverage={coverageById.get(taxon.wfo_id)}
                          onSelect={select}
                        />
                      </li>
                    ))}
                  </ul>
                  {loadMore ? <div className="flex justify-center">{loadMore}</div> : null}
                </>
              ) : searching ? (
                <EmptyState title="No matching plant" icon="search">
                  <p>
                    No curated plant matches that name. Try a scientific or pharmaceutical name.
                  </p>
                </EmptyState>
              ) : (
                <EmptyState title="No plant records" icon="leaf">
                  <p>The curated index returned no plants.</p>
                </EmptyState>
              )}
              <p className="text-xs text-muted">
                Taxonomy follows the World Flora Online identifiers stored by the backend. A common
                name can map to more than one taxon; the record shows every stored match.
              </p>
            </div>
          ) : detail.isPending ? (
            <div className="space-y-4">
              <Skeleton className="h-48 w-full rounded-2xl" />
              <Spinner label="Loading the plant record…" />
            </div>
          ) : detail.isError ? (
            <EmptyState
              title="This plant record could not be loaded"
              icon="alert"
              action={
                <Button onClick={() => void detail.refetch()} icon="retry">
                  Try again
                </Button>
              }
            >
              <p>
                The record may be unavailable or the service may be offline. No plant information is
                being inferred.
              </p>
            </EmptyState>
          ) : detail.data ? (
            <div className="animate-pop space-y-10">
              <button
                type="button"
                onClick={() => setParams({})}
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-forest-700 hover:text-forest-900 lg:hidden"
              >
                <Icon name="arrow" className="h-4 w-4 rotate-180" />
                All plants
              </button>

              <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_11rem]">
                <div className="min-w-0 space-y-10">
                  <section
                    id="overview"
                    className="relative isolate scroll-mt-6 overflow-hidden rounded-2xl bg-forest-900 p-6 text-forest-100 shadow-glow sm:p-8"
                  >
                    <div className="bg-dots absolute inset-0 -z-10 opacity-50" />
                    <BotanicalBranch className="pointer-events-none absolute -right-6 -top-6 -z-10 h-[140%] w-auto -scale-x-100 opacity-25" />
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-forest-300">
                      {detail.data.family ?? 'Family not stored'}
                    </p>
                    <h2 className="mt-2 font-display text-3xl font-semibold italic tracking-tight text-white sm:text-4xl">
                      {detail.data.scientific_name}
                    </h2>
                    <p className="mt-1 text-sm text-forest-200">
                      {detail.data.authorship ?? 'Authorship not stored'} · {detail.data.wfo_id}
                    </p>

                    <ul className="mt-6 grid gap-2 sm:grid-cols-2">
                      {detail.data.herbs.map((herb) => (
                        <li
                          key={`${herb.pharmaceutical_name}-${herb.plant_part}`}
                          className="rounded-lg bg-white/[0.07] px-3.5 py-2.5 ring-1 ring-white/10"
                        >
                          <p className="font-medium text-white">
                            {herb.common_name ?? herb.pharmaceutical_name}
                          </p>
                          <p className="text-xs text-forest-200">
                            {herb.pharmaceutical_name} · part: {herb.plant_part}
                          </p>
                        </li>
                      ))}
                    </ul>

                    <dl className="mt-6 border-t border-white/10 pt-5 text-sm">
                      <dt className="text-[11px] font-semibold uppercase tracking-wider text-forest-300">
                        Native range
                      </dt>
                      <dd className="mt-0.5 text-white">
                        {detail.data.native_range ?? 'Not stored'}
                      </dd>
                    </dl>

                    {Object.keys(detail.data.counts).length > 0 ? (
                      <div className="mt-5 rounded-lg bg-white/[0.06] p-4 ring-1 ring-white/10">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-forest-300">
                          Records stored in the index
                        </p>
                        <p className="mt-0.5 text-xs text-forest-200">
                          Counts of stored items for this plant. They are records, not study
                          findings, and a larger count does not mean stronger evidence.
                        </p>
                        <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                          {Object.entries(detail.data.counts).map(([key, value]) => (
                            <div key={key}>
                              <dt className="text-xs text-forest-200">{humanize(key)}</dt>
                              <dd className="font-display text-lg font-semibold text-white">
                                {value}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    ) : null}
                  </section>

                  {selectedCoverage ? (
                    <div id="coverage" className="scroll-mt-6">
                      <CoverageStrip row={selectedCoverage} />
                    </div>
                  ) : null}

                  <Disclosure title="Identifiers and recorded names">
                    <dl className="grid gap-3 sm:grid-cols-3">
                      {Object.entries(detail.data.identifiers)
                        .filter(([, value]) => value !== null)
                        .map(([key, value]) => (
                          <KeyValue key={key} label={humanize(key)}>
                            {String(value)}
                          </KeyValue>
                        ))}
                    </dl>
                    {detail.data.names.length > 0 ? (
                      <ul className="mt-3 flex flex-wrap gap-1.5">
                        {detail.data.names.map((name, index) => (
                          <li key={`${name.name}-${index}`}>
                            <Badge tone="neutral">
                              {name.name} · {humanize(name.name_type)}
                            </Badge>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <ProvenanceList items={detail.data.provenance} compact />
                  </Disclosure>

                  <section
                    id="regulatory"
                    aria-label="Regulatory information"
                    className="scroll-mt-6 space-y-5"
                  >
                    <div className="border-l-4 border-ev-regulatory pl-4">
                      <SectionHeading
                        eyebrow="Regulatory information"
                        title="Monographs and official uses"
                        description="Official summaries and their stated use categories. They are not HerbaGuard findings."
                      />
                    </div>
                    {detail.data.monographs.length === 0 ? (
                      <EmptyState title="No monograph stored" icon="book">
                        <p>
                          This plant has no EMA HMPC monograph in the current index. That is a
                          coverage statement, not a judgment about the plant.
                        </p>
                      </EmptyState>
                    ) : (
                      <ul className="space-y-3">
                        {detail.data.monographs.map((monograph) => (
                          <li key={`${monograph.document}-${monograph.title}`}>
                            <article className="rounded-xl border border-line bg-surface p-5 shadow-soft">
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <div>
                                  <p className="font-display text-lg font-semibold leading-snug text-ink">
                                    <ExternalLink href={monograph.url}>{monograph.title}</ExternalLink>
                                  </p>
                                  <p className="mt-0.5 text-xs text-muted">
                                    {monograph.document}
                                    {monograph.document_date
                                      ? ` · ${formatDate(monograph.document_date)}`
                                      : ''}
                                  </p>
                                </div>
                                <div className="flex flex-wrap gap-1">
                                  {monograph.use_categories.map((category) => (
                                    <Badge key={category} tone="info">
                                      {USE_CATEGORY_LABELS[category] ?? humanize(category)}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                              {Object.keys(monograph.section_completeness).length > 0 ? (
                                <p className="mt-2.5 text-xs text-muted">
                                  Sections stored:{' '}
                                  {Object.entries(monograph.section_completeness)
                                    .map(
                                      ([section, state]) =>
                                        `${humanize(section)}: ${humanize(state)}`,
                                    )
                                    .join(' · ')}
                                </p>
                              ) : null}
                              {monograph.interactions_section_states_none_reported.length > 0 ? (
                                <p className="mt-3 rounded-lg bg-surface-2 p-3 text-xs text-ink-soft">
                                  The interaction section states no interactions reported for:{' '}
                                  {monograph.interactions_section_states_none_reported.join(', ')}.
                                  This is the source’s statement, not proof of safety.
                                </p>
                              ) : null}
                            </article>
                          </li>
                        ))}
                      </ul>
                    )}

                    {detail.data.indications.length > 0 ? (
                      <div>
                        <h3 className="font-display text-lg font-semibold text-ink">
                          Recorded indications
                        </h3>
                        <ul className="mt-3 space-y-2">
                          {detail.data.indications.map((indication, index) => (
                            <li
                              key={`${indication.text}-${index}`}
                              className="rounded-lg border border-line bg-surface p-3.5 text-sm"
                            >
                              <p className="text-ink">{indication.text}</p>
                              <p className="mt-1 text-xs text-muted">
                                {USE_CATEGORY_LABELS[indication.use_category] ??
                                  humanize(indication.use_category)}{' '}
                                ·{' '}
                                <ExternalLink href={indication.evidence.url}>
                                  {indication.evidence.title}
                                </ExternalLink>
                              </p>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </section>

                  <section
                    id="evidence"
                    aria-label="Indexed clinical evidence"
                    className="scroll-mt-6 space-y-5"
                  >
                    <div className="border-l-4 border-ev-clinical pl-4">
                      <SectionHeading
                        eyebrow="Clinical evidence"
                        title="Indexed literature and other evidence"
                        description="Grouped by document type. A document type describes the evidence; it is not a quality score."
                        action={
                          evidence.data ? (
                            <Badge>{evidence.data.total} indexed items</Badge>
                          ) : null
                        }
                      />
                    </div>
                    {evidence.isPending ? (
                      <Spinner label="Loading indexed evidence…" />
                    ) : evidence.isError ? (
                      <EmptyState title="Evidence could not be loaded" icon="alert">
                        <p>
                          The evidence index is unavailable for this plant. The taxonomy and
                          regulatory sections above do not depend on it.
                        </p>
                      </EmptyState>
                    ) : evidence.data && evidence.data.items.length === 0 ? (
                      <EmptyState title="No indexed evidence" icon="file">
                        <p>
                          No evidence item is linked to this plant in the current index. This is a
                          coverage statement, not evidence of safety or ineffectiveness.
                        </p>
                      </EmptyState>
                    ) : (
                      <div className="space-y-3">
                        {EVIDENCE_GROUP_ORDER.map((key) => {
                          const items = groupedEvidence.get(key)
                          if (!items || items.length === 0) return null
                          return (
                            <Disclosure
                              key={key}
                              open={key === firstGroup}
                              title={
                                <span className="flex flex-wrap items-center gap-2.5">
                                  <span className={`h-2.5 w-2.5 rounded-full ${GROUP_DOT[key]}`} />
                                  <span className="font-semibold text-ink">
                                    {EVIDENCE_GROUPS[key].title}
                                  </span>
                                  <Badge>{items.length}</Badge>
                                </span>
                              }
                            >
                              <p className="mb-3 text-xs text-muted">
                                {EVIDENCE_GROUPS[key].description}
                              </p>
                              <ul className="space-y-2">
                                {items.map((item) => (
                                  <EvidenceItem key={item.id} item={item} />
                                ))}
                              </ul>
                            </Disclosure>
                          )
                        })}
                      </div>
                    )}
                  </section>

                  <div id="labels" className="scroll-mt-6">
                    {labels.isPending ? (
                      <div className="rounded-xl border border-line bg-surface p-5">
                        <Spinner label="Loading NIH DSLD labels…" />
                      </div>
                    ) : labels.isError ? (
                      <div className="space-y-3">
                        <ProductLabelsPanel labels={[]} />
                        <p className="text-xs text-muted">
                          The product-label endpoint is unavailable, so no label content is shown.
                          No labels are inferred from other evidence.
                        </p>
                      </div>
                    ) : (
                      <ProductLabelsPanel
                        labels={labels.data?.items ?? []}
                        total={labels.data?.total}
                      />
                    )}
                  </div>

                  <section
                    id="limits"
                    className="scroll-mt-6 rounded-xl border border-line bg-surface-2 p-6 text-sm text-ink-soft"
                  >
                    <h2 className="font-display text-lg font-semibold text-ink">
                      What this record does not tell you
                    </h2>
                    <ul className="mt-3 space-y-2">
                      {[
                        'Absence of an evidence item, monograph or product label is a coverage statement, not proof of safety.',
                        'Manufacturer label statements are not clinical evidence or HerbaGuard findings.',
                        'This record is not medical advice and does not replace a doctor or pharmacist.',
                      ].map((line) => (
                        <li key={line} className="flex gap-2.5">
                          <Icon name="info" className="mt-0.5 h-4 w-4 text-teal-600" />
                          {line}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-4 text-xs text-muted">
                      {pluralize(evidence.data?.total ?? 0, 'evidence item')} ·{' '}
                      {pluralize(labels.data?.total ?? 0, 'product label')} ·{' '}
                      {detail.data.monographs.length} monograph(s)
                    </p>
                    <p className="mt-2 text-xs text-muted">
                      Source licence states are shown in each provenance entry.
                    </p>
                  </section>
                </div>

                <nav aria-label="On this page" className="hidden xl:block">
                  <div className="sticky top-6 border-l border-line pl-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                      On this page
                    </p>
                    <ul className="mt-3 space-y-2.5 text-sm">
                      {[
                        ['#overview', 'Overview'],
                        ...(selectedCoverage ? [['#coverage', 'Coverage']] : []),
                        ['#regulatory', 'Regulatory'],
                        ['#evidence', 'Evidence'],
                        ['#labels', 'Product labels'],
                        ['#limits', 'Limits'],
                      ].map(([href, label]) => (
                        <li key={href}>
                          <a
                            href={href}
                            className="text-ink-soft transition-colors hover:text-forest-700"
                          >
                            {label}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                </nav>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
