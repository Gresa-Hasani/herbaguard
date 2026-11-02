import type { NavItem } from '../lib/constants'

/** Clearly labelled placeholder: no data is shown, so nothing can be mistaken for a finding. */
export function PlaceholderPage({ item }: { item: NavItem }) {
  return (
    <section aria-labelledby="page-heading" className="max-w-3xl">
      <h1 id="page-heading" className="text-2xl font-bold text-brand-900">
        {item.label}
      </h1>
      <p className="mt-2 text-muted">{item.description}</p>
      <p className="mt-6 rounded-lg border border-dashed border-line bg-surface p-5 text-sm text-muted">
        Not available yet — this module is built in Phase {item.phase}. No data is displayed here.
      </p>
    </section>
  )
}
