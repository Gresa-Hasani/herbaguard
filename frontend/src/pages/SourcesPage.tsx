import { Icon } from '../components/icons'
import { LicenceDetails } from '../components/LicenceDetails'
import { PublicHeader } from '../components/PublicHeader'
import { Reveal } from '../components/Reveal'
import { Badge, ButtonLink, Eyebrow, ExternalLink, Skeleton } from '../components/ui'
import { useSources } from '../hooks/useApi'
import { INTERACTION_CLASSES } from '../lib/constants'
import { licenceProfile } from '../lib/licence'
import { SOURCE_CATEGORIES, sourceMeta, PRODUCT_LABEL_NOTICE } from '../lib/sources'
import type { SourceRow } from '../lib/types'

const HIERARCHY = [
  {
    title: 'Regulatory & government evidence',
    body: 'Decides the class. A statement counts only when the source says it about this herb and this drug (or a class the drug belongs to).',
    swatch: 'bg-ev-regulatory',
  },
  {
    title: 'Clinical & scientific literature',
    body: 'Shown beside the class, grouped by document type. A document type describes a design; it is not a quality rating.',
    swatch: 'bg-ev-clinical',
  },
  {
    title: 'Supplementary research material',
    body: 'Experimental records and machine-extracted mentions add context. They never decide a class and never support “no interaction”.',
    swatch: 'bg-ev-supplementary',
  },
  {
    title: 'Manufacturer product-label information',
    body: 'Kept in its own section with a standing warning. Not clinical evidence, not used for classification.',
    swatch: 'bg-ev-manufacturer',
  },
]

const LICENCE_TERMS: { title: string; body: string; dot: string }[] = [
  {
    title: 'Licence verified',
    body: 'The registry records a verified licence for this source.',
    dot: 'bg-forest-500',
  },
  {
    title: 'Catalogue licence',
    body: 'A catalogue-level licence is recorded. It is not a verified licence: review the source’s own terms before reuse.',
    dot: 'bg-teal-500',
  },
  {
    title: 'Licence unverified',
    body: 'No verified licence is recorded. Content is shown for evidence support only and must not be republished.',
    dot: 'border-2 border-clay-600',
  },
  {
    title: 'Redistributable',
    body: 'The registry allows redistribution. It counts as confirmed only when the licence is also verified.',
    dot: 'bg-forest-300',
  },
  {
    title: 'Not redistributable',
    body: 'The registry does not allow redistribution of the source’s content.',
    dot: 'bg-clay-300',
  },
  {
    title: 'Restricted or permission required',
    body: 'Further limits apply: for example abstracts kept in a local store only, or written permission needed from the owner.',
    dot: 'bg-clay-700',
  },
]

function SourceCard({ source }: { source: SourceRow }) {
  const meta = sourceMeta(source.code)
  const profile = licenceProfile(source)
  const isManufacturer = meta.category === 'manufacturer'
  return (
    <li
      className={`flex flex-col rounded-xl border p-5 ${
        isManufacturer
          ? 'border-dashed border-clay-600/50 bg-clay-50 bg-hatch'
          : 'border-line bg-surface shadow-soft'
      }`}
    >
      <h4 className="font-display text-lg font-semibold leading-snug text-forest-950">
        <ExternalLink href={source.homepage_url}>{source.name}</ExternalLink>
      </h4>
      <p className="mt-0.5 text-xs text-muted">
        {source.provider}
        {source.is_official ? ' · official source' : ''}
      </p>

      <dl className="mt-4 space-y-3 text-sm">
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Data type
          </dt>
          <dd className="mt-0.5 text-ink">{meta.dataType}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            How it is used
          </dt>
          <dd className="mt-0.5 text-ink-soft">{meta.role}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Limitations
          </dt>
          <dd className="mt-0.5 text-ink-soft">{meta.limitation}</dd>
        </div>
      </dl>

      <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
        <LicenceDetails source={source} />
        {profile.restrictionTag ? (
          <span className="rounded-md bg-clay-50 px-2 py-1 text-[11px] font-semibold text-clay-700 ring-1 ring-clay-600/25">
            {profile.restrictionTag}
          </span>
        ) : null}
      </div>
    </li>
  )
}

export function SourcesPage() {
  const sources = useSources()
  const rows = sources.data ?? []

  return (
    <>
      <PublicHeader eyebrow="Transparency" title="Sources & methodology">
        <p>
          Where HerbaGuard’s evidence comes from, how the four kinds of material are kept apart, and
          what limits each source. The registry below is read live from the backend.
        </p>
      </PublicHeader>

      <div className="mx-auto max-w-6xl space-y-20 px-4 py-14 sm:px-6 lg:py-20">
        <section aria-labelledby="hierarchy-heading">
          <Reveal className="max-w-2xl">
            <Eyebrow>Evidence hierarchy</Eyebrow>
            <h2
              id="hierarchy-heading"
              className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950"
            >
              Four kinds of material, never blended
            </h2>
          </Reveal>
          <ol className="mt-8 grid gap-4 md:grid-cols-2">
            {HIERARCHY.map((tier, index) => (
              <Reveal as="li" key={tier.title} delay={index * 70}>
                <div className="flex h-full gap-4 rounded-xl border border-line bg-surface p-5 shadow-soft">
                  <span
                    className={`mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white ${tier.swatch}`}
                  >
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-forest-950">
                      {tier.title}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{tier.body}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </ol>
        </section>

        <section aria-labelledby="registry-heading">
          <Reveal className="max-w-2xl">
            <Eyebrow>Source registry</Eyebrow>
            <h2
              id="registry-heading"
              className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950"
            >
              Registered sources
            </h2>
            <p className="mt-3 text-ink-soft">
              Grouped by the role each source plays. Open{' '}
              <strong className="font-semibold text-ink">Licence details</strong> on any source for
              its licence status, redistribution terms and restrictions.
            </p>
            <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-forest-500" /> Verified
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-teal-500" /> Catalogue licence
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full border-2 border-clay-600" /> Unverified
              </span>
            </p>
          </Reveal>

          {sources.isPending ? (
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <Skeleton className="h-56 w-full" />
              <Skeleton className="h-56 w-full" />
            </div>
          ) : sources.isError ? (
            <div className="mt-8 flex gap-3 rounded-xl border border-danger/30 bg-danger-soft p-5 text-sm">
              <Icon name="alert" className="mt-0.5 h-4 w-4 text-danger" />
              <p>
                The source registry could not be loaded, so no source list can be shown. This does
                not change the medical disclaimer: HerbaGuard is not medical advice.
              </p>
            </div>
          ) : (
            <div className="mt-10 space-y-12">
              {SOURCE_CATEGORIES.map((category) => {
                const group = rows.filter((row) => sourceMeta(row.code).category === category.key)
                if (group.length === 0) return null
                return (
                  <Reveal key={category.key}>
                    <section aria-label={category.title}>
                      <div className="flex items-start gap-3">
                        <span className={`mt-2 h-3 w-3 shrink-0 rounded-full ${category.swatch}`} />
                        <div>
                          <h3 className="font-display text-xl font-semibold text-forest-950">
                            {category.title}
                          </h3>
                          <p className="text-sm text-muted">{category.summary}</p>
                        </div>
                      </div>
                      {category.key === 'manufacturer' ? (
                        <p className="mt-4 rounded-lg border border-clay-600/30 bg-clay-50 px-4 py-3 text-sm font-medium text-clay-800">
                          {PRODUCT_LABEL_NOTICE}
                        </p>
                      ) : null}
                      <ul className="mt-5 grid gap-4 md:grid-cols-2">
                        {group.map((source) => (
                          <SourceCard key={source.code} source={source} />
                        ))}
                      </ul>
                    </section>
                  </Reveal>
                )
              })}
            </div>
          )}
        </section>

        <section aria-labelledby="method-heading" className="max-w-3xl">
          <Reveal>
            <Eyebrow>Method</Eyebrow>
            <h2
              id="method-heading"
              className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950"
            >
              The five classes
            </h2>
            <p className="mt-3 text-sm text-ink-soft">
              Fixed rules over stored statements. A higher letter does not mean greater safety.
            </p>
            <dl className="mt-5 divide-y divide-line rounded-xl border border-line bg-surface">
              {Object.values(INTERACTION_CLASSES).map((item) => (
                <div key={item.letter} className="flex gap-4 p-4">
                  <dt>
                    <Badge className={item.badge}>{item.letter}</Badge>
                  </dt>
                  <dd>
                    <p className="text-sm font-semibold text-ink">{item.label}</p>
                    <p className="text-sm text-muted">{item.description}</p>
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </section>

        <section aria-labelledby="licence-heading" className="space-y-6">
          <Reveal className="max-w-2xl">
            <Eyebrow>Licences</Eyebrow>
            <h2
              id="licence-heading"
              className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950"
            >
              How licences are recorded
            </h2>
            <p className="mt-3 text-ink-soft">
              HerbaGuard shows each licence exactly as the registry records it. A source is never
              treated as verified, or as freely reusable, because of who provides it.
            </p>
          </Reveal>

          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {LICENCE_TERMS.map((term) => (
              <div key={term.title} className="rounded-xl border border-line bg-surface p-4">
                <dt className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${term.dot}`} />
                  {term.title}
                </dt>
                <dd className="mt-1.5 text-sm leading-relaxed text-ink-soft">{term.body}</dd>
              </div>
            ))}
          </dl>

          <p className="max-w-3xl text-sm leading-relaxed text-muted">
            NIH DSLD labels are marked <strong>licence unverified</strong> and{' '}
            <strong>not redistributable</strong> in this instance. Manufacturer statements are
            attributed to the manufacturer, are not used for A–E classification, and this interface
            provides no public export of label content. Licence labels reflect the backend registry
            at page load and are not legal advice.
          </p>
        </section>


        <Reveal>
          <section className="rounded-xl border border-line bg-surface p-6 shadow-soft">
            <h2 className="font-display text-xl font-semibold text-forest-950">Traceability</h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-soft">
              Every statement and label exposes its source code, licence state, retrieval URL,
              retrieval time, extraction method and source version where recorded. When a source or
              section is missing, the interface says so instead of filling the gap.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <ButtonLink to="/interactions" iconEnd="arrow">
                Check an interaction
              </ButtonLink>
              <ButtonLink to="/about" variant="secondary">
                About HerbaGuard
              </ButtonLink>
            </div>
          </section>
        </Reveal>
      </div>
    </>
  )
}
