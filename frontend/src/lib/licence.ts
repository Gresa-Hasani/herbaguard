import { formatDateTime } from './format'
import { sourceMeta } from './sources'
import type { SourceRow } from './types'

/**
 * Licence presentation derived from the backend registry. The registry's own status is shown as
 * recorded: this module never upgrades a licence, never infers permissions from a provider's
 * reputation, and reports unrecorded metadata as "not recorded".
 */
export type LicenceState = 'verified' | 'catalogue' | 'unverified'

export type RedistributionKind =
  | 'redistributable'
  | 'pending'
  | 'not_redistributable'
  | 'local_only'
  | 'permission_required'

export interface LicenceProfile {
  state: LicenceState
  stateLabel: string
  stateMeaning: string
  redistribution: { kind: RedistributionKind; label: string; detail: string }
  /** Short marker for a card, only when the source carries a restriction. */
  restrictionTag: string | null
  attribution: string
  licenceText: string
  licenceUrl: string | null
  sourceUrl: string | null
  accessMethod: string
  retrievedAt: string
  version: string
  notes: string[]
}

const STATE_LABELS: Record<LicenceState, string> = {
  verified: 'Licence verified',
  catalogue: 'Catalogue licence',
  unverified: 'Licence unverified',
}

const STATE_MEANINGS: Record<LicenceState, string> = {
  verified: 'The registry records a verified licence for this source.',
  catalogue:
    'A catalogue-level licence is recorded. It is not a verified licence: review the source’s own terms before reuse.',
  unverified:
    'No verified licence is recorded. The content is shown for evidence support only and must not be republished.',
}

export function licenceState(status: string): LicenceState {
  if (status === 'verified') return 'verified'
  if (status === 'catalogue') return 'catalogue'
  return 'unverified'
}

const ACCESS_METHODS: Record<string, string> = {
  api: 'Programmatic API',
  download: 'Dataset download',
  pdf: 'PDF documents',
  web_page: 'Web pages',
  repository: 'Project repository',
  internal: 'Generated inside HerbaGuard',
}

export function licenceProfile(source: SourceRow): LicenceProfile {
  const meta = sourceMeta(source.code)
  const state = licenceState(source.licence_status)

  let redistribution: LicenceProfile['redistribution']
  if (meta.restriction === 'permission_required') {
    redistribution = {
      kind: 'permission_required',
      label: 'Permission required',
      detail: 'Redistribution needs the owner’s written permission.',
    }
  } else if (meta.restriction === 'local_only') {
    redistribution = {
      kind: 'local_only',
      label: 'Restricted: local store only',
      detail: 'Content is kept in the local store and is not redistributed.',
    }
  } else if (!source.redistributable) {
    redistribution = {
      kind: 'not_redistributable',
      label: 'Not redistributable',
      detail: 'The registry does not allow redistribution of this source’s content.',
    }
  } else if (state === 'verified') {
    redistribution = {
      kind: 'redistributable',
      label: 'Redistributable',
      detail: 'Recorded as redistributable, with a verified licence.',
    }
  } else {
    redistribution = {
      kind: 'pending',
      label: 'Recorded as redistributable, not confirmed',
      detail:
        'The registry marks this source redistributable, but its licence is not verified, so this is not confirmed permission.',
    }
  }

  const restrictionTag =
    redistribution.kind === 'permission_required'
      ? 'Permission required'
      : redistribution.kind === 'local_only'
        ? 'Local store only'
        : redistribution.kind === 'not_redistributable'
          ? 'Not redistributable'
          : null

  return {
    state,
    stateLabel: STATE_LABELS[state],
    stateMeaning: STATE_MEANINGS[state],
    redistribution,
    restrictionTag,
    attribution:
      source.attribution ?? meta.attribution ?? 'No attribution requirement is recorded.',
    licenceText: source.licence ?? 'No licence text is recorded.',
    licenceUrl: source.licence_url ?? null,
    sourceUrl: source.homepage_url,
    accessMethod: source.access_method
      ? (ACCESS_METHODS[source.access_method] ?? source.access_method)
      : 'Not recorded',
    retrievedAt: source.latest_retrieved_at
      ? formatDateTime(source.latest_retrieved_at)
      : 'No retrieval date is recorded.',
    version: source.latest_source_version ?? 'No version is recorded.',
    notes: meta.licenceNotes,
  }
}
