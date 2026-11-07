import { Badge } from './ui'
import type { EvidenceTypeInfo } from '../lib/types'
import { licenceLabel, licenceTone } from '../lib/format'

export function EvidenceTypeBadge({ info }: { info: EvidenceTypeInfo | null }) {
  if (!info) return <Badge>Type not stated</Badge>
  return (
    <span
      className="inline-flex flex-wrap items-center gap-1"
      title={`${info.note} This is a document or study type, not a quality rating.`}
    >
      <Badge tone="neutral">{info.label}</Badge>
      <span className="text-[11px] text-muted">type, not quality</span>
    </span>
  )
}

export function LicenceBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${licenceTone(status)}`}
    >
      {licenceLabel(status)}
    </span>
  )
}

export function RedistributionBadge({ allowed }: { allowed: boolean }) {
  return (
    <Badge tone={allowed ? 'brand' : 'danger'}>
      {allowed ? 'Redistribution allowed' : 'Not redistributable'}
    </Badge>
  )
}
