import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { licenceProfile, type LicenceProfile, type LicenceState } from '../lib/licence'
import type { SourceRow } from '../lib/types'
import { Icon } from './icons'
import { ExternalLink } from './ui'

const DOT: Record<LicenceState, string> = {
  verified: 'bg-forest-500',
  catalogue: 'bg-teal-500',
  unverified: 'border-2 border-clay-600 bg-transparent',
}

const STATE_BADGE: Record<LicenceState, string> = {
  verified: 'border-forest-600/30 bg-forest-50 text-forest-700',
  catalogue: 'border-teal-600/30 bg-teal-50 text-teal-700',
  unverified: 'border-clay-600/30 bg-clay-50 text-clay-700',
}

export function LicenceStatusBadge({ state, label }: { state: LicenceState; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${STATE_BADGE[state]}`}
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[state]}`} />
      {label}
    </span>
  )
}

const FOCUSABLE =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input, select, textarea'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-0.5 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</dt>
      <dd className="text-sm leading-relaxed text-ink">{children}</dd>
    </div>
  )
}

/** Modal panel: a bottom sheet on phones and a side drawer on larger screens. */
function LicencePanel({
  source,
  profile,
  onClose,
}: {
  source: SourceRow
  profile: LicenceProfile
  onClose: () => void
}) {
  const titleId = useId()
  const panel = useRef<HTMLDivElement | null>(null)
  // Keep the latest handler without re-running the focus and key setup on every render.
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus()

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab' || !panel.current) return
      const focusable = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const redistributionTone =
    profile.redistribution.kind === 'redistributable'
      ? 'text-forest-700'
      : profile.redistribution.kind === 'pending'
        ? 'text-ink'
        : 'text-clay-700'

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:justify-end">
      <div
        aria-hidden="true"
        onClick={() => closeRef.current()}
        className="animate-pop absolute inset-0 bg-forest-950/50 backdrop-blur-[2px]"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="animate-pop relative flex max-h-[88vh] w-full flex-col rounded-t-2xl bg-surface shadow-lift sm:h-full sm:max-h-none sm:w-[31rem] sm:rounded-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line p-5">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-teal-700">
              Licence details
            </p>
            <h2 id={titleId} className="mt-1 font-display text-xl font-semibold text-forest-950">
              {source.name}
            </h2>
            <p className="text-xs text-muted">{source.provider}</p>
          </div>
          <button
            type="button"
            data-autofocus
            onClick={() => closeRef.current()}
            aria-label="Close licence details"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <Icon name="x" />
          </button>
        </header>

        <div className="scrollbar-thin flex-1 overflow-y-auto p-5">
          <div className="flex flex-wrap gap-2">
            <LicenceStatusBadge state={profile.state} label={profile.stateLabel} />
            <span
              className={`inline-flex items-center rounded-md border border-line bg-surface-2 px-2 py-0.5 text-xs font-medium ${redistributionTone}`}
            >
              {profile.redistribution.label}
            </span>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-ink-soft">{profile.stateMeaning}</p>

          <dl className="mt-4 divide-y divide-line border-y border-line">
            <Row label="Licence (as recorded)">{profile.licenceText}</Row>
            <Row label="Redistribution">
              <span className="font-medium">{profile.redistribution.label}.</span>{' '}
              {profile.redistribution.detail}
            </Row>
            <Row label="Attribution">{profile.attribution}</Row>
            <Row label="Terms or licence URL">
              {profile.licenceUrl ? (
                <ExternalLink href={profile.licenceUrl}>{profile.licenceUrl}</ExternalLink>
              ) : (
                'No licence URL is recorded.'
              )}
            </Row>
            <Row label="Source URL">
              {profile.sourceUrl ? (
                <ExternalLink href={profile.sourceUrl} className="break-all">
                  {profile.sourceUrl}
                </ExternalLink>
              ) : (
                'No source URL is recorded.'
              )}
            </Row>
            <Row label="Access">{profile.accessMethod}</Row>
            <Row label="Latest retrieval">{profile.retrievedAt}</Row>
            <Row label="Latest item version">
              {profile.version}
              {source.latest_source_version ? (
                <span className="mt-0.5 block text-xs text-muted">
                  The version of the most recently retrieved item, which can be a document
                  identifier rather than a version of the whole source.
                </span>
              ) : null}
            </Row>
          </dl>

          <section aria-label="Restrictions and open questions" className="mt-5">
            <h3 className="font-display text-base font-semibold text-ink">
              Restrictions and open questions
            </h3>
            <ul className="mt-2 space-y-2 text-sm leading-relaxed text-ink-soft">
              {profile.notes.map((note) => (
                <li key={note} className="flex gap-2.5">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-clay-600" />
                  {note}
                </li>
              ))}
              {profile.state === 'unverified' ? (
                <li className="flex gap-2.5">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-clay-600" />
                  The licence is not verified. Check the source’s terms before any reuse or
                  redistribution.
                </li>
              ) : null}
            </ul>
          </section>

          <p className="mt-6 text-xs leading-relaxed text-muted">
            Shown as recorded in the backend registry at page load. This is not legal advice, and
            nothing here is inferred from the provider’s reputation or from being a government
            source.
          </p>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** Compact, discoverable trigger: a status dot and "Licence details"; the panel opens on demand. */
export function LicenceDetails({
  source,
  label = 'Licence details',
  variant = 'chip',
}: {
  source: SourceRow
  label?: string
  variant?: 'chip' | 'link'
}) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const profile = licenceProfile(source)

  function close() {
    setOpen(false)
    trigger.current?.focus()
  }

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${label} for ${source.name}: ${profile.stateLabel}`}
        onClick={() => setOpen(true)}
        className={
          variant === 'chip'
            ? 'group inline-flex items-center gap-2 rounded-md border border-line-strong bg-surface px-2.5 py-1 text-xs font-semibold text-ink-soft transition-colors hover:border-forest-500 hover:bg-forest-50 hover:text-forest-800'
            : 'inline-flex items-center gap-1.5 text-xs font-semibold text-teal-700 underline-offset-2 hover:underline'
        }
      >
        <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[profile.state]}`} />
        {label}
        <Icon
          name="chevron"
          className="h-3 w-3 -rotate-90 text-muted transition-transform group-hover:translate-x-0.5"
        />
      </button>
      {open ? <LicencePanel source={source} profile={profile} onClose={close} /> : null}
    </>
  )
}
