import { classMeta, humanize, pluralize, sourceLabel } from '../lib/format'
import type { DrugCheckResult } from '../lib/types'
import { ClassBadge } from './ClassBadge'
import { Icon } from './icons'
import { StatementCard } from './StatementCard'
import { Alert, Badge, Disclosure, EmptyState, KeyValue } from './ui'

const BAND: Record<string, string> = {
  A: 'border-l-class-a bg-class-a/[0.06]',
  B: 'border-l-class-b bg-class-b/[0.06]',
  C: 'border-l-class-c bg-class-c/[0.06]',
  D: 'border-l-class-d bg-class-d/[0.06]',
  E: 'border-l-class-e bg-class-e/[0.07]',
}

export function InteractionResult({ result }: { result: DrugCheckResult }) {
  const { drug, classification } = result
  const meta = classMeta(classification.interaction_class)
  const isNoEvidence = classification.interaction_class === 'D'
  const isInsufficient = classification.interaction_class === 'E'

  return (
    <article className="animate-pop overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
      <div
        className={`flex flex-wrap items-center justify-between gap-5 border-l-[6px] p-5 sm:p-6 ${BAND[meta.letter]}`}
      >
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Medication
          </p>
          <h3 className="mt-1 font-display text-2xl font-semibold leading-tight text-ink">
            {drug.drug?.name ?? drug.query}
            {drug.drug ? (
              <span className="ml-2 font-sans text-sm font-normal text-muted">
                RxCUI {drug.drug.rxcui}
              </span>
            ) : null}
          </h3>
          {drug.status !== 'resolved' ? (
            <p className="mt-1 text-sm text-danger">
              Drug resolution: {humanize(drug.status)}
              {drug.note ? ` — ${drug.note}` : ''}
            </p>
          ) : null}
        </div>
        <div className="sm:text-right">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Interaction class
          </p>
          <div className="mt-1.5">
            <ClassBadge
              letter={classification.interaction_class}
              label={classification.class_label}
              size="lg"
            />
          </div>
        </div>
      </div>

      <div className="space-y-6 p-5 sm:p-6">
        <div>
          <p className="font-display text-xl font-semibold text-ink">
            {classification.finding_label}
          </p>
          <p className="mt-2 max-w-3xl leading-relaxed text-ink-soft">
            {classification.explanation}
          </p>
        </div>

        {isNoEvidence ? (
          <Alert tone="warn" title="No interaction evidence is not evidence of safety">
            <p>
              The sources searched did not contain an interaction statement for this pair. That does
              not show the combination is safe, and it does not replace advice from a doctor or
              pharmacist.
            </p>
          </Alert>
        ) : null}

        {isInsufficient ? (
          <Alert tone="warn" title="This pair could not be assessed">
            <p>
              The available evidence was insufficient to classify this combination. Treat the result
              as unknown rather than reassuring.
            </p>
          </Alert>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-xl bg-surface-2 p-4">
            <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-forest-700">
              <Icon name="scale" className="h-4 w-4" />
              Deterministic reasons
            </h4>
            {classification.reasons.length > 0 ? (
              <ul className="mt-2.5 space-y-2 text-sm text-ink">
                {classification.reasons.map((reason) => (
                  <li key={reason} className="flex gap-2.5">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-500" />
                    {reason}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted">No additional reasons were returned.</p>
            )}
          </section>
          <section className="rounded-xl border border-clay-600/20 bg-clay-50 p-4">
            <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-clay-700">
              <Icon name="alert" className="h-4 w-4" />
              Caveats and uncertainty
            </h4>
            {classification.caveats.length > 0 ? (
              <ul className="mt-2.5 space-y-2 text-sm text-ink">
                {classification.caveats.map((caveat) => (
                  <li key={caveat} className="flex gap-2.5">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-clay-600" />
                    {caveat}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted">No caveats were returned.</p>
            )}
          </section>
        </div>

        {classification.severity_wordings.length > 0 ? (
          <div className="rounded-xl border border-line p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">
              Source severity wording
            </p>
            <ul className="mt-2 flex flex-wrap gap-2 text-sm text-ink">
              {classification.severity_wordings.map((wording) => (
                <li
                  key={wording}
                  className="rounded-md bg-surface-3 px-2.5 py-1 font-display italic"
                >
                  “{wording}”
                </li>
              ))}
            </ul>
            <p className="mt-2.5 text-xs text-muted">
              These are the source authors’ words, shown verbatim. HerbaGuard does not convert them
              into a severity score.
            </p>
          </div>
        ) : null}

        <p className="text-xs leading-relaxed text-muted">
          <span className="font-semibold uppercase tracking-wider">Evidence strength.</span>{' '}
          Evidence strength is not reduced to a number. Each decisive statement below names its
          document type; document type is not a quality rating.
        </p>

        <section>
          <h4 className="flex items-baseline gap-2 font-display text-xl font-semibold text-ink">
            Decisive statements
            <span className="font-sans text-sm font-normal text-muted">
              ({pluralize(result.decisive_statements.length, 'statement')})
            </span>
          </h4>
          {result.decisive_statements.length > 0 ? (
            <ul className="mt-4 space-y-3">
              {result.decisive_statements.map((statement) => (
                <li key={statement.id}>
                  <StatementCard statement={statement} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-4">
              <EmptyState title="No decisive statement" icon="file">
                <p>
                  No stored statement was strong enough to determine this class. The classification
                  and its caveats above are the complete result; do not read this as safety.
                </p>
              </EmptyState>
            </div>
          )}
        </section>

        <div className="space-y-2.5">
          {result.context_statements.length > 0 ? (
            <Disclosure
              title={`Context statements (${result.context_statements.length}) — not used as confirmed interactions`}
            >
              <ul className="space-y-3">
                {result.context_statements.map((statement) => (
                  <li key={statement.id}>
                    <StatementCard statement={statement} />
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}

          {result.mechanism_assessment ? (
            <Disclosure title={`Mechanism assessment — ${result.mechanism_assessment.label}`}>
              <p className="text-sm text-ink-soft">{result.mechanism_assessment.explanation}</p>
              <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                <KeyValue label="Stored mechanism paths">
                  {result.mechanism_assessment.paths_total}
                </KeyValue>
                <KeyValue label="Qualifying paths">
                  {result.mechanism_assessment.qualifying_paths}
                </KeyValue>
                <KeyValue label="Assessment finding">
                  {result.mechanism_assessment.finding}
                </KeyValue>
              </dl>
              <p className="mt-2 text-xs text-muted">{result.mechanism_assessment.rules}</p>
              {result.mechanism_paths.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {result.mechanism_paths.map((path, index) => (
                    <li
                      key={`${path.target_symbols}-${index}`}
                      className="rounded-lg bg-surface-2 p-3 text-sm"
                    >
                      <p className="font-medium text-ink">{path.target_symbols}</p>
                      <p className="mt-1 text-ink-soft">{path.description}</p>
                      <p className="mt-1 text-xs text-muted">
                        Qualifies for class B: {path.qualifies_for_class_b ? 'yes' : 'no'}
                        {path.conflicting ? ' · conflicting evidence' : ''}
                        {path.experimental ? ' · experimental' : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Disclosure>
          ) : null}

          <Disclosure title={`Sources searched (${result.sources_searched.length})`}>
            <ul className="space-y-2.5 text-sm">
              {result.sources_searched.map((source) => (
                <li
                  key={source.source_code}
                  className="flex flex-wrap items-center justify-between gap-2"
                >
                  <span>
                    <span className="font-medium text-ink">{sourceLabel(source.source_code)}</span>{' '}
                    <span className="text-muted">— {source.description}</span>
                  </span>
                  <Badge tone={source.used_for_classification ? 'brand' : 'neutral'}>
                    {source.used_for_classification ? 'Used for classification' : 'Not decisive'}
                  </Badge>
                </li>
              ))}
            </ul>
          </Disclosure>

          <Disclosure title="Classification method">
            <p className="whitespace-pre-line text-sm text-ink-soft">{classification.method}</p>
          </Disclosure>
        </div>
      </div>
    </article>
  )
}
