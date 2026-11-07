import { Icon, type IconName } from '../components/icons'
import { PublicHeader } from '../components/PublicHeader'
import { Reveal } from '../components/Reveal'
import { ButtonLink, Eyebrow } from '../components/ui'
import { useMeta } from '../hooks/useApi'

const PRINCIPLES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'scale',
    title: 'What it does',
    body: 'Resolves herbs and medications to curated identifiers, retrieves stored source statements, applies deterministic A–E classification rules, and exposes citations and caveats.',
  },
  {
    icon: 'compass',
    title: 'Who it is for',
    body: 'Demonstration and research use: exploring what regulatory and scientific sources say, and how a finding is assembled. It is not a clinical decision-support device.',
  },
  {
    icon: 'shield',
    title: 'What it refuses',
    body: 'Personal advice, dosing, diagnosis and emergency guidance. Questions in those categories are declined or referred rather than answered.',
  },
]

const LIMITATIONS = [
  'Coverage is finite. A plant, drug, interaction or label that is absent from the index is not evidence of safety or absence of an effect.',
  'Class D means no interaction evidence was found in the sources searched; class E means the pair could not be assessed. Neither is a safety assurance.',
  'Evidence type describes a document or study design. It is not a quality grade, and HerbaGuard does not pool studies into an effect estimate.',
  'Source statements can be ambiguous, outdated or contradicted by other sources. Caveats and context statements are displayed rather than hidden.',
  'The Evidence Assistant can make mistakes. Its output passes retrieval and validation rules, but validation cannot guarantee clinical correctness.',
  'HerbaGuard does not provide doses, treatment plans, diagnoses or emergency care, and it does not replace a doctor or pharmacist.',
]

const OUT_OF_SCOPE = [
  'Personal medical advice or a recommendation to start, stop or change a medicine',
  'Dose calculation or substitution of a prescribed medicine',
  'Diagnosis of a condition or interpretation of laboratory results',
  'Guarantees that a combination is safe because no interaction was retrieved',
  'Publishing or redistributing source content whose licence has not been verified',
]

export function AboutPage() {
  const meta = useMeta()

  return (
    <>
      <PublicHeader eyebrow="Purpose, scope and limits" title="About HerbaGuard">
        <p>
          HerbaGuard is an evidence-support tool for exploring herb–drug interactions and the
          sources behind them. It retrieves stored regulatory and scientific material, classifies
          interactions with fixed rules, and shows the exact statements and provenance used. It is
          not a diagnostic or treatment system.
        </p>
      </PublicHeader>

      <div className="mx-auto max-w-6xl space-y-20 px-4 py-14 sm:px-6 lg:py-20">
        <section className="grid gap-5 md:grid-cols-3">
          {PRINCIPLES.map((item, index) => (
            <Reveal key={item.title} delay={index * 80}>
              <article className="h-full rounded-xl border border-line bg-surface p-6 shadow-soft">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-forest-800 text-forest-100">
                  <Icon name={item.icon} className="h-5 w-5" />
                </span>
                <h2 className="mt-4 font-display text-xl font-semibold text-forest-950">
                  {item.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{item.body}</p>
              </article>
            </Reveal>
          ))}
        </section>

        <section aria-labelledby="limitations-heading" className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>Read before relying on a result</Eyebrow>
            <h2
              id="limitations-heading"
              className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950"
            >
              Limitations
            </h2>
            <p className="mt-3 text-ink-soft">
              These limits apply to every page, including the deterministic checker.
            </p>
          </Reveal>
          <ol className="space-y-3">
            {LIMITATIONS.map((limitation, index) => (
              <Reveal as="li" key={limitation} delay={index * 50}>
                <div className="flex gap-4 rounded-xl border border-line bg-surface p-4 text-sm leading-relaxed text-ink-soft">
                  <span className="font-display text-lg font-semibold text-clay-600">
                    {index + 1}
                  </span>
                  <span>{limitation}</span>
                </div>
              </Reveal>
            ))}
          </ol>
        </section>

        <section className="grid gap-5 lg:grid-cols-2">
          <Reveal>
            <div className="h-full rounded-xl border border-clay-600/30 bg-clay-50 p-6">
              <h2 className="font-display text-xl font-semibold text-clay-800">Out of scope</h2>
              <ul className="mt-3 space-y-2.5 text-sm text-ink-soft">
                {OUT_OF_SCOPE.map((item) => (
                  <li key={item} className="flex gap-3">
                    <Icon name="x" className="mt-0.5 h-4 w-4 text-clay-600" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <div className="h-full rounded-xl border border-line bg-surface p-6 shadow-soft">
              <h2 className="font-display text-xl font-semibold text-forest-950">
                Data and privacy
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                This instance has no user accounts. Interaction checks send only the selected herb
                and medication names to the HerbaGuard backend. Assistant questions are sent to the
                backend for retrieval and, when configured, model generation and validation. Do not
                submit personal health information.
              </p>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                The interface does not enable external drug lookup. Unknown medication names are
                reported as unresolved rather than silently sent to another service.
              </p>
              <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
                {meta.data?.disclaimer ??
                  'HerbaGuard provides information from scientific and regulatory sources. It is not medical advice and does not replace your doctor or pharmacist.'}
              </p>
            </div>
          </Reveal>
        </section>

        <Reveal>
          <div className="flex flex-wrap items-center justify-between gap-5 rounded-xl bg-forest-900 p-7 text-forest-100 shadow-glow">
            <div className="max-w-xl">
              <h2 className="font-display text-2xl font-semibold text-white">
                See where the evidence comes from
              </h2>
              <p className="mt-1 text-sm text-forest-200">
                The registry lists every source, how it is used and what limits it.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <ButtonLink
                to="/sources"
                iconEnd="arrow"
                className="!bg-white !text-forest-900 hover:!bg-forest-50"
              >
                Sources &amp; methodology
              </ButtonLink>
              <ButtonLink
                to="/interactions"
                variant="ghost"
                className="!text-white ring-1 ring-white/30 hover:!bg-white/10"
              >
                Open workspace
              </ButtonLink>
            </div>
          </div>
        </Reveal>
      </div>
    </>
  )
}
