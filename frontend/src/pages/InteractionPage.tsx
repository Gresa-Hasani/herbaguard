import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ClassBadge } from '../components/ClassBadge'
import { DrugPicker } from '../components/DrugPicker'
import { HerbPicker } from '../components/HerbPicker'
import { Icon } from '../components/icons'
import { InteractionResult } from '../components/InteractionResult'
import {
  Alert,
  Badge,
  Button,
  Disclosure,
  PageHeader,
  Skeleton,
  Spinner,
} from '../components/ui'
import { useInteractionCheck } from '../hooks/useApi'
import { ApiError } from '../lib/api'
import { INTERACTION_CLASSES } from '../lib/constants'
import type { Drug, HerbRef } from '../lib/types'

function ClassLegend() {
  return (
    <div>
      <p className="text-sm text-ink-soft">
        Fixed decision rules over stored statements. A higher letter does not mean greater safety.
      </p>
      <dl className="mt-4 divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {Object.values(INTERACTION_CLASSES).map((item) => (
          <div key={item.letter} className="flex items-start gap-4 p-4">
            <dt className="pt-0.5">
              <ClassBadge letter={item.letter} label="" size="md" />
            </dt>
            <dd>
              <p className="text-sm font-semibold text-ink">{item.label}</p>
              <p className="mt-0.5 text-sm text-muted">{item.description}</p>
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 flex gap-2.5 rounded-lg bg-clay-50 p-3 text-xs leading-relaxed text-clay-800">
        <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Class D and class E are not evidence of safety. Class A is a reported interaction or
        contraindication, not a prediction of what will happen to an individual.
      </p>
    </div>
  )
}

export function InteractionPage() {
  const [herb, setHerb] = useState<HerbRef | null>(null)
  const [drugs, setDrugs] = useState<Drug[]>([])
  const [clientMs, setClientMs] = useState<number | null>(null)
  const check = useInteractionCheck()
  const resultsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (check.isSuccess || check.isError) {
      // Bring the outcome into view on narrow screens where the form fills the viewport.
      if (window.innerWidth < 1024) {
        resultsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      }
    }
  }, [check.isSuccess, check.isError])

  function resetResult() {
    if (check.isSuccess || check.isError) check.reset()
    setClientMs(null)
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!herb || drugs.length === 0 || check.isPending) return
    const started = performance.now()
    check.mutate(
      { herb: herb.pharmaceutical_name, drugs: drugs.map((drug) => drug.name) },
      {
        onSuccess: () => setClientMs(Math.round(performance.now() - started)),
      },
    )
  }

  const error = check.error
  const errorMessage =
    error instanceof ApiError
      ? error.message
      : error
        ? 'The interaction check could not be completed.'
        : null
  const canSubmit = Boolean(herb) && drugs.length > 0 && !check.isPending
  const showIdle = !check.isPending && !check.isSuccess && !errorMessage

  return (
    <div className="space-y-8">
      <PageHeader
        icon="pill"
        eyebrow="Deterministic evidence check"
        title="Interaction Checker"
        aside={
          <Badge tone="brand" className="self-start">
            <Icon name="scale" className="h-3.5 w-3.5" />
            Fixed rules · no language model
          </Badge>
        }
      >
        <p>
          Select one herb from the curated index and up to five medications. HerbaGuard searches
          stored regulatory and literature statements and returns the backend’s A–E class with the
          statements that determined it. No language model is used for this check.
        </p>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)] lg:items-start xl:grid-cols-[26rem_minmax(0,1fr)]">
        <form
          onSubmit={submit}
          aria-describedby="checker-help"
          className="rounded-2xl border border-line bg-surface p-5 shadow-soft sm:p-6 lg:sticky lg:top-6"
        >
          <div className="space-y-7">
            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-forest-800 text-xs font-bold text-white">
                1
              </span>
              <div className="min-w-0 flex-1">
                <HerbPicker
                  selected={herb}
                  onSelect={(next) => {
                    setHerb(next)
                    resetResult()
                  }}
                  onClear={() => {
                    setHerb(null)
                    resetResult()
                  }}
                />
              </div>
            </div>
            <div className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-forest-800 text-xs font-bold text-white">
                2
              </span>
              <div className="min-w-0 flex-1">
                <DrugPicker
                  selected={drugs}
                  onChange={(next) => {
                    setDrugs(next)
                    resetResult()
                  }}
                />
              </div>
            </div>
          </div>

          <div className="mt-7 border-t border-line pt-5">
            <Button
              type="submit"
              size="lg"
              disabled={!canSubmit}
              className="w-full"
              icon={check.isPending ? undefined : 'shield'}
            >
              {check.isPending ? 'Checking…' : 'Check interaction'}
            </Button>
            <p id="checker-help" className="mt-2.5 text-xs leading-relaxed text-muted">
              {canSubmit
                ? 'The check uses the herb’s pharmaceutical name. Classification comes only from the backend.'
                : 'Select one herb and at least one medication to run the check.'}
            </p>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              External drug lookup is disabled in this interface. If a medication is not in the
              index, it is not silently guessed or fetched from another service.
            </p>
          </div>
        </form>

        <div ref={resultsRef} aria-live="polite" className="min-w-0 scroll-mt-20 space-y-5">
          {check.isPending ? (
            <div className="rounded-2xl border border-line bg-surface p-6 shadow-soft">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Spinner label="Checking stored evidence…" />
                <Badge tone="brand">Deterministic pipeline</Badge>
              </div>
              <p className="mt-2 text-sm text-muted">
                Resolving the herb and medication names, retrieving stored statements and applying
                the classification rules. No generative model is running for this step.
              </p>
              <div className="mt-5 flex items-center gap-5">
                <Skeleton className="h-16 w-16 rounded-xl" />
                <div className="flex-1 space-y-2.5">
                  <Skeleton className="h-4 w-1/2" />
                  <Skeleton className="h-3 w-5/6" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            </div>
          ) : null}

          {errorMessage ? (
            <Alert tone="danger" role="alert" title="The interaction check failed">
              <p>{errorMessage}</p>
              {error instanceof ApiError && error.requestId ? (
                <p className="mt-1 text-xs">Request ID: {error.requestId}</p>
              ) : null}
              <p className="mt-2 text-xs">
                No result is being shown, so nothing on this page should be read as reassurance about
                the combination. Check the service status and try again.
              </p>
            </Alert>
          ) : null}

          {check.isSuccess && check.data ? (
            <section aria-labelledby="results-heading" className="space-y-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2
                    id="results-heading"
                    className="font-display text-3xl font-semibold tracking-tight text-ink"
                  >
                    Result for {check.data.herb.herb?.common_name ?? check.data.herb.query}
                  </h2>
                  <p className="mt-1 text-sm text-muted">
                    Herb resolution: {check.data.herb.status}
                    {check.data.herb.note ? ` — ${check.data.herb.note}` : ''}
                    {clientMs !== null ? ` · round-trip ${clientMs} ms` : ''}
                  </p>
                </div>
                <Badge tone="neutral">Backend class, not computed in the browser</Badge>
              </div>

              {check.data.herb.status !== 'resolved' ? (
                <Alert tone="warn" title="The herb was not resolved unambiguously">
                  <p>
                    The backend could not map the herb name to a single curated taxon. Any classes
                    below are limited to what could be assessed; an unresolved herb is not a safe
                    result.
                  </p>
                </Alert>
              ) : null}

              {check.data.results.length === 0 ? (
                <Alert tone="warn" title="No medication results returned">
                  <p>
                    The backend returned no drug results. This is not evidence that the combination
                    is safe.
                  </p>
                </Alert>
              ) : (
                <ul className="space-y-5">
                  {check.data.results.map((result) => (
                    <li key={result.drug.query}>
                      <InteractionResult result={result} />
                    </li>
                  ))}
                </ul>
              )}

              <Alert tone="neutral" role="note">
                <p>{check.data.disclaimer}</p>
              </Alert>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="text-muted">Need the evidence behind a result?</span>
                <Link
                  to="/explorer"
                  className="inline-flex items-center gap-1.5 font-semibold text-forest-700 hover:text-forest-900"
                >
                  Open the Herb Explorer
                  <Icon name="arrow" className="h-4 w-4" />
                </Link>
                <Link
                  to="/assistant"
                  className="inline-flex items-center gap-1.5 font-semibold text-forest-700 hover:text-forest-900"
                >
                  Ask about the evidence
                  <Icon name="arrow" className="h-4 w-4" />
                </Link>
              </div>
            </section>
          ) : null}

          {check.isSuccess && check.data ? (
            <Disclosure title="What the classes mean">
              <ClassLegend />
            </Disclosure>
          ) : null}

          {showIdle ? (
            <section
              aria-label="How the interaction classes work"
              className="animate-pop rounded-2xl border border-line bg-surface-2 p-6"
            >
              <h2 className="font-display text-2xl font-semibold text-ink">
                What the classes mean
              </h2>
              <div className="mt-3">
                <ClassLegend />
              </div>
              <p className="mt-5 text-xs leading-relaxed text-muted">
                The Explorer shows the full herb record, regulatory monographs and indexed evidence.
                Manufacturer product labels are kept separate and are never used in classification.
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}
