import type { Provenance } from '../lib/types'
import { formatDateTime, licenceLabel } from '../lib/format'
import { Icon } from './icons'
import { ExternalLink } from './ui'

export function ProvenanceList({
  items,
  compact = false,
}: {
  items: Provenance[]
  compact?: boolean
}) {
  if (items.length === 0) return null
  return (
    <details className="group mt-3 text-xs text-muted">
      <summary className="inline-flex items-center gap-1.5 font-semibold text-teal-700 hover:text-teal-600">
        <Icon
          name="chevron"
          className="h-3.5 w-3.5 -rotate-90 transition-transform duration-200 group-open:rotate-0"
        />
        Source provenance ({items.length})
      </summary>
      <ul className="animate-pop mt-2 space-y-2">
        {items.map((item, index) => (
          <li
            key={`${item.source_code}-${item.location ?? index}`}
            className="rounded-lg border border-line bg-surface-2 p-3"
          >
            <p className="font-medium text-ink">
              {item.source_name}{' '}
              <span className="font-normal text-muted">({item.source_code})</span>
            </p>
            <p className="mt-1">
              {licenceLabel(item.licence_status)}
              {item.licence ? ` · ${item.licence}` : ''}
            </p>
            {item.location ? <p className="mt-1">Location: {item.location}</p> : null}
            {!compact ? (
              <p className="mt-1">
                Retrieved {formatDateTime(item.retrieved_at)} · method {item.extraction_method}
                {item.source_version ? ` · version ${item.source_version}` : ''}
              </p>
            ) : null}
            <p className="mt-1 break-all">
              <ExternalLink href={item.retrieved_url}>{item.retrieved_url}</ExternalLink>
            </p>
          </li>
        ))}
      </ul>
    </details>
  )
}
