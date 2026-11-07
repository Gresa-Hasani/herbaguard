import {
  EVIDENCE_GROUPS,
  INTERACTION_CLASSES,
  SOURCE_LABELS,
  type EvidenceGroupKey,
  type InteractionClassMeta,
} from './constants'

export function humanize(value: string | null | undefined): string {
  if (!value) return 'Not stated'
  return value.replace(/_/g, ' ').replace(/^\w/, (character: string) => character.toUpperCase())
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Date not stated'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric' }).format(
    date,
  )
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function sourceLabel(code: string | null | undefined): string {
  if (!code) return 'Unknown source'
  return SOURCE_LABELS[code] ?? code
}

export function classMeta(letter: string | null | undefined): InteractionClassMeta {
  if (letter === 'A' || letter === 'B' || letter === 'C' || letter === 'D' || letter === 'E') {
    return INTERACTION_CLASSES[letter]
  }
  return INTERACTION_CLASSES.E
}

export function evidenceGroup(code: string | null | undefined): EvidenceGroupKey {
  switch (code) {
    case 'REG':
    case 'GOV':
      return 'regulatory'
    case 'SR':
    case 'RCT':
    case 'CLIN':
    case 'CASE':
    case 'REV':
      return 'human'
    case 'ANIMAL':
    case 'INVITRO':
    case 'COMP':
      return 'laboratory'
    default:
      return 'other'
  }
}

export function groupTitle(key: EvidenceGroupKey): string {
  return EVIDENCE_GROUPS[key].title
}

export function groupDescription(key: EvidenceGroupKey): string {
  return EVIDENCE_GROUPS[key].description
}

export function licenceTone(status: string): string {
  if (status === 'verified') return 'border-forest-600/30 bg-forest-50 text-forest-700'
  if (status === 'catalogue') return 'border-teal-600/30 bg-teal-50 text-teal-700'
  return 'border-clay-600/30 bg-clay-50 text-clay-700'
}

export function licenceLabel(status: string): string {
  if (status === 'verified') return 'Licence verified'
  if (status === 'catalogue') return 'Catalogue licence'
  return 'Licence unverified'
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}
