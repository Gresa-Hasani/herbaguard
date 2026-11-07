import { STATEMENT_TYPE_LABELS, USE_CATEGORY_LABELS } from '../lib/constants'
import { humanize, sourceLabel } from '../lib/format'
import type { Statement } from '../lib/types'
import { EvidenceTypeBadge } from './EvidenceBadges'
import { Icon } from './icons'
import { ProvenanceList } from './ProvenanceList'
import { Badge, ExternalLink, KeyValue } from './ui'

export function StatementCard({ statement }: { statement: Statement }) {
  const target =
    statement.matched_via === 'class' && statement.drug_class
      ? `${statement.drug_class.code} · ${statement.drug_class.name}`
      : statement.drug?.name ?? statement.object_label_verbatim
  const decisive = statement.role === 'decisive'

  return (
    <article
      className={`rounded-xl border bg-surface p-4 shadow-soft sm:p-5 ${
        decisive ? 'border-l-4 border-line border-l-ev-regulatory' : 'border-line'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={decisive ? 'brand' : 'neutral'}>
            {decisive ? 'Decisive statement' : 'Context statement'}
          </Badge>
          <Badge tone="neutral">
            {STATEMENT_TYPE_LABELS[statement.statement_type] ?? humanize(statement.statement_type)}
          </Badge>
          <Badge tone="info">{sourceLabel(statement.source_code)}</Badge>
        </div>
        <EvidenceTypeBadge info={statement.evidence.evidence_type} />
      </div>

      {statement.excerpt ? (
        <blockquote className="relative mt-4 rounded-lg bg-surface-2 py-3 pl-11 pr-4 font-display text-[15px] leading-relaxed text-ink">
          <Icon name="quote" className="absolute left-3.5 top-3.5 h-4 w-4 text-forest-400" />“
          {statement.excerpt}”
        </blockquote>
      ) : (
        <p className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-muted">
          No verbatim excerpt is stored for this statement.
        </p>
      )}

      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <KeyValue label="About">
          {target} ({statement.matched_via === 'class' ? 'drug class' : 'drug'})
        </KeyValue>
        <KeyValue label="Use category">
          {USE_CATEGORY_LABELS[statement.use_category] ?? humanize(statement.use_category)}
        </KeyValue>
        <KeyValue label="Source section">{statement.source_section ?? 'Not stated'}</KeyValue>
        {statement.severity_wording ? (
          <KeyValue label="Source wording (verbatim)">
            <span className="font-medium">“{statement.severity_wording}”</span>
          </KeyValue>
        ) : null}
        {statement.conditions ? (
          <div className="sm:col-span-2 lg:col-span-3">
            <KeyValue label="Conditions">{statement.conditions}</KeyValue>
          </div>
        ) : null}
        {statement.mechanism ? (
          <div className="sm:col-span-2 lg:col-span-3">
            <KeyValue label="Mechanism (source)">{statement.mechanism}</KeyValue>
          </div>
        ) : null}
        {statement.subject_check !== 'not_applicable' ? (
          <KeyValue label="Subject check">
            {humanize(statement.subject_check)}
            {statement.subject_check_note ? ` — ${statement.subject_check_note}` : ''}
          </KeyValue>
        ) : null}
      </dl>

      {statement.subject_check === 'not_verified' ? (
        <p className="mt-3 flex gap-2 rounded-lg border border-clay-600/30 bg-clay-50 p-3 text-xs text-clay-800">
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          The source sentence does not confirm that this drug is its subject. This statement is
          context only, not a confirmed interaction.
        </p>
      ) : null}

      <div className="mt-4 border-t border-line pt-3 text-sm">
        <p className="font-medium text-ink">
          <ExternalLink href={statement.evidence.url}>{statement.evidence.title}</ExternalLink>
        </p>
        <p className="mt-1 text-xs text-muted">
          {statement.evidence.external_id}
          {statement.evidence.document_date
            ? ` · ${statement.evidence.document_date}`
            : statement.evidence.publication_year
              ? ` · ${statement.evidence.publication_year}`
              : ''}
        </p>
        <ProvenanceList items={statement.provenance} />
      </div>
    </article>
  )
}
