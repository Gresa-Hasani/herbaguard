import { Link } from 'react-router-dom'

import { NAV_ITEMS } from '../lib/constants'

export function HomePage() {
  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <h1 className="text-3xl font-bold tracking-tight text-brand-900">
          What is known about combining a herbal medicine with a drug?
        </h1>
        <p className="mt-4 text-lg text-muted">
          HerbaGuard brings together regulatory monographs, drug labels and the scientific
          literature, shows how strong the evidence is, and links every statement to its source.
        </p>
      </section>

      <section aria-labelledby="modules-heading">
        <h2 id="modules-heading" className="sr-only">
          Modules
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <Link
                to={item.to}
                className="block h-full rounded-lg border border-line bg-surface p-5 transition hover:border-brand-600"
              >
                <h3 className="font-semibold text-ink">{item.label}</h3>
                <p className="mt-1 text-sm text-muted">{item.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-line bg-surface p-5 text-sm text-muted">
        <h2 className="font-semibold text-ink">Project status</h2>
        <p className="mt-1">
          This is the project foundation (Phase 1). Data ingestion, interaction analysis and the
          evidence assistant are built in later phases; no scientific findings are shown yet.
        </p>
      </section>
    </div>
  )
}
