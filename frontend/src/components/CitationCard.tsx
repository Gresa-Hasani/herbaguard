import { useSources } from '../hooks/useApi'
import {
  documentType,
  evidenceCategory,
  GENERATED_SOURCE_TIP,
  isGenerated,
  licenceStatusPlain,
  qualifierDetails,
  recordType,
  RESTRICTION_TIPS,
  sourceTip,
  studyContext,
} from '../lib/citations'
import { licenceLabel, licenceTone, sourceLabel } from '../lib/format'
import { licenceProfile } from '../lib/licence'
import { sourceMeta } from '../lib/sources'
import type { Citation } from '../lib/types'
import { Icon } from './icons'
import { LicenceDetails } from './LicenceDetails'
import { ProvenanceList } from './ProvenanceList'
import { Tooltip } from './Tooltip'
import { Alert, ExternalLink } from './ui'

const REFERENCE_TIP =
  'Reference ID: links this source to the statements in the answer. It is not an evidence-quality rating.'

/** Pill badge look shared by every metadata label; the explanation is in the tooltip. */
const PILL =
  'inline-flex max-w-full items-center rounded-md border px-2.5 py-1 text-sm leading-snug cursor-help transition-colors focus-visible:outline-offset-1'
const NEUTRAL = `${PILL} border-line bg-surface-2 text-ink-soft hover:border-line-strong hover:bg-sage-100`
const REFERENCE = `${PILL} border-forest-600/40 bg-forest-50 font-semibold text-forest-800 hover:bg-forest-100`
const RESTRICTED = `${PILL} border-clay-600/40 bg-clay-50 text-clay-700 hover:bg-clay-100`

function FieldList({ fields }: { fields: { label: string; value: string }[] }) {
  return (
    <dl className="divide-y divide-line">
      {fields.map((field) => (
        <div key={field.label} className="grid gap-0.5 py-2 sm:grid-cols-[9rem_1fr] sm:gap-4">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            {field.label}
          </dt>
          <dd className="text-sm leading-relaxed text-ink">{field.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * One citation, in the same compact structure for every kind: a row of badges (reference id,
 * record type, evidence category, document type, source, licence), each explained by a tooltip on
 * hover, focus or tap; then, for external sources, the title and the cited passage; then a
 * collapsed "More about this citation". HerbaGuard's own classification has the same badges, and
 * its full result sits in the collapsed details. Only labels the citation supports are shown.
 */
export function CitationCard({ citation }: { citation: Citation }) {
  const sources = useSources()
  const isProductLabel = citation.kind === 'product_label'
  const generated = isGenerated(citation)
  const record = recordType(citation)
  const category = evidenceCategory(citation)
  const documentInfo = documentType(citation.evidence_type)
  const study = studyContext(citation)
  const { fields: recorded, notes } = qualifierDetails(citation.qualifiers)

  const provenance = citation.provenance[0]
  const registryRow = sources.data?.find((row) => row.code === citation.source_code)
  const profile = registryRow ? licenceProfile(registryRow) : null
  const meta = citation.source_code ? sourceMeta(citation.source_code) : null
  const fullName = provenance?.source_name ?? null
  // The short registry label ("DDID experimental records") is the badge; the registered name is
  // in its tooltip and in the provenance below.
  const shortName = citation.source_code ? sourceLabel(citation.source_code) : fullName
  const restriction = profile?.restrictionTag ?? null

  return (
    <li
      id={`citation-${citation.label}`}
      data-citation-kind={citation.kind}
      className={`scroll-mt-24 rounded-xl border p-4 shadow-soft target:ring-2 target:ring-teal-500 sm:p-5 ${
        isProductLabel
          ? 'bg-hatch border-dashed border-clay-600/50 bg-clay-50'
          : 'border-line bg-surface'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Tooltip text={REFERENCE_TIP} icon={false} triggerClassName={REFERENCE}>
          {citation.label}
        </Tooltip>
        <Tooltip text={record.description} icon={false} triggerClassName={NEUTRAL}>
          {record.label}
        </Tooltip>
        <Tooltip text={category.description} icon={false} triggerClassName={NEUTRAL}>
          {category.label}
        </Tooltip>
        {documentInfo ? (
          <Tooltip text={documentInfo.description} icon={false} triggerClassName={NEUTRAL}>
            {documentInfo.label}
          </Tooltip>
        ) : null}
        {shortName ? (
          <Tooltip
            icon={false}
            triggerClassName={NEUTRAL}
            text={sourceTip(
              fullName ?? shortName,
              meta && meta.category !== 'other' ? meta.dataType : null,
              registryRow?.provider ?? null,
            )}
          >
            {shortName}
          </Tooltip>
        ) : (
          <Tooltip
            icon={false}
            triggerClassName={NEUTRAL}
            text={generated ? GENERATED_SOURCE_TIP : 'No source is recorded for this item.'}
          >
            {generated ? 'HerbaGuard rules' : 'Not recorded'}
          </Tooltip>
        )}
        {provenance ? (
          <Tooltip
            text={licenceStatusPlain(provenance.licence_status)}
            icon={false}
            triggerClassName={`${PILL} ${licenceTone(provenance.licence_status)} hover:brightness-95`}
          >
            {licenceLabel(provenance.licence_status)}
          </Tooltip>
        ) : null}
        {restriction ? (
          <Tooltip
            text={RESTRICTION_TIPS[restriction] ?? restriction}
            icon={false}
            triggerClassName={RESTRICTED}
          >
            {restriction}
          </Tooltip>
        ) : null}
        {registryRow ? <LicenceDetails source={registryRow} variant="link" /> : null}
      </div>

      {generated ? null : (
        <>
          <p className="mt-3 font-semibold leading-snug text-ink">
            <ExternalLink href={citation.url}>{citation.title ?? 'Untitled source'}</ExternalLink>
          </p>
          {citation.external_id || citation.location ? (
            <p className="mt-0.5 break-words text-xs text-muted">
              {citation.external_id}
              {citation.external_id && citation.location ? ' · ' : ''}
              {citation.location}
            </p>
          ) : null}
        </>
      )}

      {isProductLabel ? (
        <div className="mt-3">
          <Alert tone="warn" title="Manufacturer label information">
            <p>
              Manufacturer label information — not clinical evidence, not a HerbaGuard finding.
              Licence unverified.
            </p>
          </Alert>
        </div>
      ) : null}

      {generated ? null : (
        <blockquote className="mt-3 rounded-lg border-l-4 border-forest-400 bg-surface-2 p-3.5 font-display text-[15px] leading-relaxed text-ink">
          “{citation.excerpt}”
        </blockquote>
      )}

      <details className="group mt-2 text-sm">
        <summary className="inline-flex items-center gap-1.5 py-1 text-xs font-semibold text-teal-700 hover:text-teal-600">
          <Icon
            name="chevron"
            className="h-3.5 w-3.5 -rotate-90 transition-transform duration-200 group-open:rotate-0"
          />
          More about this citation
        </summary>
        <div className="animate-pop mt-2 space-y-4 rounded-lg border border-line bg-surface-2 p-3.5">
          {generated ? (
            <section aria-label="Classification result">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Classification result
              </h4>
              <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-ink">
                {citation.excerpt}
              </p>
            </section>
          ) : null}

          {study.length > 0 ? (
            <section aria-label="Study context">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Study context
              </h4>
              <FieldList fields={study} />
              <p className="mt-1 text-xs text-muted">
                As recorded in the dataset; nothing here is inferred.
              </p>
            </section>
          ) : citation.kind === 'observation' ? (
            <section aria-label="Study context">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Study context
              </h4>
              <p className="mt-1 text-sm text-ink-soft">
                No study details (species, design, sample size, duration or methods) could be read
                from this record.
              </p>
            </section>
          ) : null}

          {recorded.length > 0 ? (
            <section aria-label="Recorded details">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Recorded details
              </h4>
              <FieldList fields={recorded} />
            </section>
          ) : null}

          {notes.length > 0 ? (
            <section aria-label="Notes">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Notes
              </h4>
              <ul className="mt-1 space-y-1 text-xs text-ink-soft">
                {notes.map((note) => (
                  <li key={note} className="flex gap-1.5">
                    <span aria-hidden="true">•</span>
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {provenance ? (
            <section aria-label="Licence as recorded">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Licence as recorded
              </h4>
              <p className="mt-1 text-sm text-ink">
                {provenance.licence ?? 'No licence text is recorded.'}
              </p>
            </section>
          ) : null}

          <ProvenanceList items={citation.provenance} compact />
        </div>
      </details>
    </li>
  )
}
