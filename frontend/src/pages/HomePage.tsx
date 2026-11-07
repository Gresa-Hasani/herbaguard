import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { BotanicalBranch, LeafOrnament, SpecimenPlate } from '../components/BotanicalArt'
import { ClassBadge } from '../components/ClassBadge'
import { Icon, type IconName } from '../components/icons'
import { Reveal } from '../components/Reveal'
import { ButtonLink, Eyebrow } from '../components/ui'
import { INTERACTION_CLASSES } from '../lib/constants'

const TRUST_POINTS: { icon: IconName; text: string }[] = [
  { icon: 'scale', text: 'Deterministic A–E classes' },
  { icon: 'quote', text: 'Every statement cited' },
  { icon: 'shield', text: 'Uncertainty stated, never hidden' },
]

const STEPS: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'search',
    title: 'Your question or selection',
    body: 'Choose a herb and medications, or ask in plain language. Names are resolved to curated identifiers and are never guessed.',
  },
  {
    icon: 'database',
    title: 'Evidence retrieval',
    body: 'Stored regulatory statements, drug labels and indexed literature are searched. Product labels stay out of classification.',
  },
  {
    icon: 'scale',
    title: 'Evidence assessment',
    body: 'Fixed rules assign the A–E class from the retrieved statements. No language model decides the class.',
  },
  {
    icon: 'file',
    title: 'Traceable results',
    body: 'Each result carries its reasons, caveats, verbatim excerpts and provenance, with a link back to the source document.',
  },
]

const TIERS: {
  title: string
  body: string
  dot: string
  box: string
  tag?: string
}[] = [
  {
    title: 'Regulatory & government evidence',
    body: 'EMA herbal monographs, NCCIH fact sheets and FDA drug labels. Official statements, quoted verbatim with their section.',
    dot: 'bg-ev-regulatory',
    box: 'border-line bg-surface',
  },
  {
    title: 'Clinical & scientific literature',
    body: 'Indexed publications grouped by document type. A type describes a design; it is not a quality score.',
    dot: 'bg-ev-clinical',
    box: 'border-line bg-surface',
  },
  {
    title: 'Supplementary research material',
    body: 'Experimental interaction records and machine-extracted literature mentions. Context only: never decides a class and never shown as proof.',
    dot: 'bg-ev-supplementary',
    box: 'border-line bg-surface',
  },
  {
    title: 'Manufacturer product-label information',
    body: 'NIH DSLD labels describe products, not study findings. Not clinical evidence and not a HerbaGuard finding. Licence unverified.',
    dot: 'bg-ev-manufacturer',
    box: 'border-dashed border-clay-600/50 bg-clay-50 bg-hatch',
    tag: 'Not clinical evidence',
  },
]

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="bg-dots-dark pointer-events-none absolute inset-0 opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]"
      />
      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-12 sm:px-6 lg:grid-cols-[1.02fr_1fr] lg:gap-14 lg:pb-28 lg:pt-20">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-forest-600/20 bg-forest-50 px-3 py-1 text-xs font-semibold text-forest-700">
            <Icon name="leaf" className="h-3.5 w-3.5" />
            EthnoHack 2026 · Digital Health &amp; Phytotherapy
          </span>
          <h1 className="mt-6 font-display text-[2.75rem] font-semibold leading-[1.04] tracking-tight text-forest-950 sm:text-6xl">
            Herb–drug evidence you can trace to its source.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft">
            HerbaGuard turns regulatory monographs, drug labels and scientific records into
            transparent interaction findings. Every class is explained, every statement is cited,
            and what is not known is said plainly.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <ButtonLink to="/interactions" size="lg" iconEnd="arrow" className="w-full sm:w-auto">
              Check an interaction
            </ButtonLink>
            <ButtonLink to="/explorer" size="lg" variant="secondary" className="w-full sm:w-auto">
              Explore medicinal plants
            </ButtonLink>
          </div>
          <ul className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-ink-soft">
            {TRUST_POINTS.map((point) => (
              <li key={point.text} className="flex items-center gap-2">
                <Icon name={point.icon} className="h-4 w-4 text-forest-600" />
                {point.text}
              </li>
            ))}
          </ul>
        </div>
        <SpecimenPlate />
      </div>
    </section>
  )
}

function Capabilities() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-24">
      <Reveal className="max-w-2xl">
        <Eyebrow>Three ways in</Eyebrow>
        <h2 className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950 sm:text-4xl">
          One evidence base, three working tools.
        </h2>
        <p className="mt-4 text-ink-soft">
          Each tool reads the same stored sources and keeps their hierarchy intact. None of them
          turns missing evidence into reassurance.
        </p>
      </Reveal>

      <div className="mt-12 grid gap-5 lg:grid-cols-6">
        {/* Interaction checking */}
        <Reveal className="lg:col-span-4">
          <article className="group relative h-full overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-soft transition-shadow hover:shadow-lift sm:p-8">
            <div className="grid gap-8 md:grid-cols-[1fr_1.05fr] md:items-center">
              <div>
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-forest-800 text-forest-100">
                  <Icon name="pill" className="h-5 w-5" />
                </span>
                <h3 className="mt-5 font-display text-2xl font-semibold text-forest-950">
                  Interaction checking
                </h3>
                <p className="mt-3 leading-relaxed text-ink-soft">
                  Select a herb and up to five medications. A fixed rule set returns an A–E class
                  with the exact statements that determined it, the caveats around it and the
                  mechanisms that may explain it.
                </p>
                <Link
                  to="/interactions"
                  className="group/link mt-5 inline-flex items-center gap-2 font-semibold text-forest-700 hover:text-forest-900"
                >
                  Open the checker
                  <Icon
                    name="arrow"
                    className="h-4 w-4 transition-transform group-hover/link:translate-x-1"
                  />
                </Link>
              </div>
              <div
                aria-hidden="true"
                className="rounded-xl border border-line bg-surface-2 p-4"
              >
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  The five classes
                </p>
                <ul className="mt-3 space-y-2">
                  {Object.values(INTERACTION_CLASSES).map((item) => (
                    <li
                      key={item.letter}
                      className="flex items-center gap-3 rounded-lg bg-surface px-3 py-2 shadow-soft"
                    >
                      <ClassBadge letter={item.letter} label={item.label} size="sm" />
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-muted">
                  D and E mean “no evidence found” or “not assessable”, never “safe”.
                </p>
              </div>
            </div>
          </article>
        </Reveal>

        {/* Plant exploration */}
        <Reveal className="lg:col-span-2" delay={90}>
          <article className="relative h-full overflow-hidden rounded-2xl border border-line bg-sage-100 p-6 transition-shadow hover:shadow-lift sm:p-8">
            <LeafOrnament className="pointer-events-none absolute -right-6 -top-6 h-44 w-44 text-forest-600/15" />
            <span className="relative flex h-11 w-11 items-center justify-center rounded-xl bg-teal-700 text-white">
              <Icon name="leaf" className="h-5 w-5" />
            </span>
            <h3 className="relative mt-5 font-display text-2xl font-semibold text-forest-950">
              Plant exploration
            </h3>
            <p className="relative mt-3 leading-relaxed text-ink-soft">
              Taxonomy, recorded names, monographs and indexed evidence for each supported
              medicinal plant, grouped by what kind of evidence it is.
            </p>
            <dl className="relative mt-6 space-y-2 text-sm" aria-hidden="true">
              {['Taxonomy and names', 'Regulatory information', 'Evidence by type', 'Product labels, kept apart'].map(
                (row) => (
                  <div
                    key={row}
                    className="flex items-center gap-2.5 rounded-lg bg-white/70 px-3 py-2 text-ink-soft"
                  >
                    <Icon name="check" className="h-4 w-4 text-forest-600" />
                    {row}
                  </div>
                ),
              )}
            </dl>
            <Link
              to="/explorer"
              className="group/link relative mt-6 inline-flex items-center gap-2 font-semibold text-forest-700 hover:text-forest-900"
            >
              Explore plants
              <Icon
                name="arrow"
                className="h-4 w-4 transition-transform group-hover/link:translate-x-1"
              />
            </Link>
          </article>
        </Reveal>

        {/* Evidence assistant */}
        <Reveal className="lg:col-span-6" delay={60}>
          <article className="relative overflow-hidden rounded-2xl bg-forest-900 p-6 text-forest-100 shadow-glow sm:p-8">
            <div className="bg-dots pointer-events-none absolute inset-0 opacity-50" />
            <div className="relative grid gap-8 md:grid-cols-[1fr_1.1fr] md:items-center">
              <div>
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 text-forest-100 ring-1 ring-white/15">
                  <Icon name="chat" className="h-5 w-5" />
                </span>
                <h3 className="mt-5 font-display text-2xl font-semibold text-white">
                  Evidence Assistant
                </h3>
                <p className="mt-3 max-w-md leading-relaxed text-forest-200">
                  Ask in plain language. The assistant answers only from retrieved evidence, links
                  every paragraph to the passages it cites, and is checked against validation
                  rules before anything is shown.
                </p>
                <Link
                  to="/assistant"
                  className="group/link mt-5 inline-flex items-center gap-2 font-semibold text-white hover:text-forest-200"
                >
                  Ask a question
                  <Icon
                    name="arrow"
                    className="h-4 w-4 transition-transform group-hover/link:translate-x-1"
                  />
                </Link>
              </div>
              <div
                aria-hidden="true"
                className="space-y-3 rounded-xl bg-white/[0.06] p-4 ring-1 ring-white/10"
              >
                <div className="ml-auto max-w-[85%] rounded-xl rounded-br-sm bg-forest-700 px-4 py-2.5 text-sm text-white">
                  What does the evidence say about St John&rsquo;s wort and warfarin?
                </div>
                <div className="rounded-xl rounded-bl-sm bg-canvas p-4">
                  <div className="space-y-2">
                    <div className="h-2.5 w-full rounded bg-sage-200" />
                    <div className="h-2.5 w-11/12 rounded bg-sage-200" />
                    <div className="h-2.5 w-3/5 rounded bg-sage-200" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-semibold">
                    <span className="rounded bg-teal-50 px-1.5 py-0.5 text-teal-700">C1</span>
                    <span className="rounded bg-teal-50 px-1.5 py-0.5 text-teal-700">S3</span>
                    <span className="rounded bg-teal-50 px-1.5 py-0.5 text-teal-700">S4</span>
                    <span className="rounded bg-[#ece9f6] px-1.5 py-0.5 text-ev-supplementary">
                      X1
                    </span>
                  </div>
                  <p className="mt-3 text-[11px] text-muted">
                    Layout illustration: paragraphs link to numbered, retrievable sources.
                  </p>
                </div>
              </div>
            </div>
          </article>
        </Reveal>
      </div>
    </section>
  )
}

function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 border-y border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-24">
        <Reveal className="max-w-2xl">
          <Eyebrow>How it works</Eyebrow>
          <h2 className="mt-2 font-display text-3xl font-semibold tracking-tight text-forest-950 sm:text-4xl">
            From a question to a result you can check.
          </h2>
        </Reveal>

        <ol className="relative mt-14 grid gap-10 md:grid-cols-4 md:gap-6">
          <div
            aria-hidden="true"
            className="absolute left-[12%] top-[1.55rem] hidden h-px w-[76%] bg-line-strong md:block"
          />
          {STEPS.map((step, index) => (
            <Reveal
              as="li"
              key={step.title}
              delay={index * 110}
              className={`relative flex gap-5 md:block ${
                index < STEPS.length - 1
                  ? 'max-md:after:absolute max-md:after:-bottom-10 max-md:after:left-[1.55rem] max-md:after:top-[3.1rem] max-md:after:w-px max-md:after:bg-line-strong'
                  : ''
              }`}
            >
              <span className="relative flex h-[3.1rem] w-[3.1rem] shrink-0 items-center justify-center rounded-full border border-forest-600/30 bg-forest-50 text-forest-700 ring-4 ring-surface">
                <Icon name={step.icon} className="h-5 w-5" />
                <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-forest-800 text-[11px] font-bold text-white">
                  {index + 1}
                </span>
              </span>
              <div className="pt-1 md:pt-0">
                <h3 className="font-display text-lg font-semibold text-forest-950 md:mt-5">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{step.body}</p>
              </div>
            </Reveal>
          ))}
        </ol>

        <Reveal className="mt-14">
          <div className="flex gap-3 rounded-xl border border-teal-600/25 bg-teal-50 p-5 text-sm leading-relaxed text-ink">
            <Icon name="info" className="mt-0.5 h-5 w-5 text-teal-600" />
            <p>
              <strong className="font-semibold">Where a language model is used.</strong> Only in the
              Evidence Assistant, to phrase an answer from retrieved passages. Its output is
              validated against the citations and safety rules before display, and the A–E class is
              always copied from the deterministic checker.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function EvidenceFirst() {
  return (
    <section id="evidence" className="scroll-mt-20 mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-24">
      <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <Reveal>
          <Eyebrow>Evidence-first</Eyebrow>
          <h2 className="mt-2 font-display text-3xl font-semibold leading-tight tracking-tight text-forest-950 sm:text-4xl">
            Missing evidence is not safety.
          </h2>
          <p className="mt-5 leading-relaxed text-ink-soft">
            HerbaGuard keeps four kinds of material apart, labels each one, and never lets a weaker
            kind stand in for a stronger one. When nothing is found, the result says so, and it does
            not read that silence as reassurance.
          </p>
          <ul className="mt-7 space-y-3 text-sm">
            {[
              'Class D means no interaction evidence was found, not that a combination is safe.',
              'Product labels describe products. They are never clinical evidence.',
              'Machine-extracted mentions are context. They never confirm or rule out an interaction.',
            ].map((line) => (
              <li key={line} className="flex gap-3 text-ink-soft">
                <Icon name="shield" className="mt-0.5 h-4 w-4 text-forest-600" />
                {line}
              </li>
            ))}
          </ul>
          <ButtonLink to="/sources" variant="secondary" className="mt-8" iconEnd="arrow">
            Sources &amp; methodology
          </ButtonLink>
        </Reveal>

        <ol className="space-y-3">
          {TIERS.map((tier, index) => (
            <Reveal as="li" key={tier.title} delay={index * 90}>
              <div
                className={`flex gap-4 rounded-xl border p-5 shadow-soft transition-transform duration-200 hover:-translate-y-0.5 ${tier.box}`}
              >
                <span className="mt-1.5 flex flex-col items-center gap-1.5">
                  <span className={`h-3 w-3 rounded-full ${tier.dot}`} />
                  {index < TIERS.length - 1 ? <span className="h-full w-px bg-line-strong" /> : null}
                </span>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-display text-lg font-semibold text-forest-950">
                      {tier.title}
                    </h3>
                    {tier.tag ? (
                      <span className="rounded-md border border-clay-600/40 bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-clay-700">
                        {tier.tag}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{tier.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section className="px-4 pb-20 sm:px-6">
      <Reveal>
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl bg-forest-900 px-6 py-14 text-center shadow-glow sm:px-12 sm:py-20">
          <div className="bg-dots pointer-events-none absolute inset-0 opacity-50" />
          <BotanicalBranch className="pointer-events-none absolute -right-10 -top-10 h-[130%] w-auto opacity-25" />
          <div className="relative mx-auto max-w-2xl">
            <h2 className="font-display text-3xl font-semibold leading-tight tracking-tight text-white sm:text-5xl">
              Start with the evidence.
            </h2>
            <p className="mt-5 text-lg text-forest-200">
              Check a combination, read what the sources actually say, and see exactly where each
              statement comes from.
            </p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <ButtonLink
                to="/interactions"
                size="lg"
                iconEnd="arrow"
                className="w-full !bg-white !text-forest-900 hover:!bg-forest-50 sm:w-auto"
              >
                Check an interaction
              </ButtonLink>
              <ButtonLink
                to="/explorer"
                size="lg"
                variant="ghost"
                className="w-full !text-white ring-1 ring-white/30 hover:!bg-white/10 sm:w-auto"
              >
                Explore medicinal plants
              </ButtonLink>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

export function HomePage() {
  const { hash } = useLocation()

  useEffect(() => {
    if (!hash) return
    const target = document.getElementById(hash.slice(1))
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  return (
    <>
      <Hero />
      <Capabilities />
      <HowItWorks />
      <EvidenceFirst />
      <FinalCta />
    </>
  )
}
