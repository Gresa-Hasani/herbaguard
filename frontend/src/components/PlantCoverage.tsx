import { coverageTotals } from '../lib/coverage'
import type { TaxonCoverage } from '../lib/types'
import { Icon, type IconName } from './icons'
import { Disclosure } from './ui'

/**
 * Coverage presentation. The four groups are kept apart on purpose: a taxonomic record is not
 * evidence, regulatory material is not literature, and manufacturer product labels are not
 * clinical evidence. Missing data is shown as "none stored", never as "safe".
 */

type Group = 'regulatory' | 'literature' | 'labels'

const GROUP_STYLE: Record<Group, { on: string; dot: string }> = {
  regulatory: { on: 'border-ev-regulatory/30 bg-teal-50 text-ev-regulatory', dot: 'bg-ev-regulatory' },
  literature: { on: 'border-ev-clinical/30 bg-[#e9eef8] text-ev-clinical', dot: 'bg-ev-clinical' },
  labels: { on: 'border-clay-600/40 bg-clay-50 text-clay-700', dot: 'bg-ev-manufacturer' },
}

function Chip({
  group,
  present,
  label,
  absent,
  title,
}: {
  group: Group
  present: boolean
  label: string
  absent: string
  title: string
}) {
  const style = GROUP_STYLE[group]
  return (
    <li
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
        present ? style.on : 'border-dashed border-line-strong text-muted'
      }`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${present ? style.dot : 'border border-line-strong'}`}
      />
      {present ? label : absent}
    </li>
  )
}

/** Compact per-plant indicators for a tile in the plant list. */
export function CoverageChips({ row }: { row: TaxonCoverage }) {
  const t = coverageTotals(row)
  return (
    <ul aria-label="Stored material for this plant" className="flex flex-wrap gap-1.5">
      <Chip
        group="regulatory"
        present={t.regulatory > 0}
        label="Regulatory"
        absent="No regulatory record"
        title="EMA monographs, NCCIH fact sheets and openFDA drug-label mentions"
      />
      <Chip
        group="literature"
        present={t.literature > 0}
        label="Indexed literature"
        absent="No indexed literature"
        title="PubMed records indexed for this plant"
      />
      <Chip
        group="labels"
        present={t.labels > 0}
        label="Product labels"
        absent="No product label"
        title="NIH DSLD manufacturer labels: not clinical evidence"
      />
    </ul>
  )
}

function Facts({
  icon,
  title,
  accent,
  present,
  children,
  none,
}: {
  icon: IconName
  title: string
  accent: string
  present: boolean
  children: React.ReactNode
  none: string
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        present ? `border-line bg-surface shadow-soft ${accent}` : 'border-dashed border-line-strong bg-surface-2'
      }`}
    >
      <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
        <Icon name={icon} className="h-4 w-4" />
        {title}
      </p>
      <div className="mt-2 text-sm leading-relaxed text-ink-soft">
        {present ? children : <p className="text-muted">{none}</p>}
      </div>
    </div>
  )
}

/** What is stored for one plant, by kind of material, with explicit "none stored" states. */
export function CoverageStrip({ row }: { row: TaxonCoverage }) {
  const t = coverageTotals(row)
  const supplementary = Object.entries(row.supplementary_sources)
  const names: Record<string, string> = { ddid: 'DDID', supp_ai: 'Supp.AI', livertox: 'LiverTox' }
  return (
    <section aria-label="Coverage for this plant" className="space-y-3">
      <div>
        <h2 className="font-display text-lg font-semibold text-ink">What is stored for this plant</h2>
        <p className="text-xs text-muted">
          Four kinds of material, reported separately. “None stored” is a coverage statement, not a
          finding about the plant.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Facts
          icon="compass"
          title="Taxonomic record"
          accent="border-l-4 border-l-forest-500"
          present
          none=""
        >
          <p>
            Accepted {row.taxonomic_status === 'accepted' ? 'species' : 'taxon'} in World Flora
            Online. A taxonomic record is identity information, not evidence.
          </p>
        </Facts>
        <Facts
          icon="book"
          title="Regulatory material"
          accent="border-l-4 border-l-ev-regulatory"
          present={t.regulatory > 0}
          none="No regulatory record stored (EMA monograph, NCCIH fact sheet or openFDA label mention)."
        >
          <ul className="space-y-0.5">
            <li>EMA monograph documents: {row.monograph_documents}</li>
            <li>NCCIH fact-sheet items: {row.fact_sheet_items}</li>
            <li>openFDA drug-label mentions: {row.drug_label_mentions}</li>
          </ul>
        </Facts>
        <Facts
          icon="flask"
          title="Indexed scientific literature"
          accent="border-l-4 border-l-ev-clinical"
          present={t.literature > 0}
          none="No PubMed records are indexed for this plant."
        >
          <ul className="space-y-0.5">
            <li>Clinical-evidence search records: {row.literature_clinical_items}</li>
            <li>Interaction search records: {row.literature_interaction_items}</li>
          </ul>
          <p className="mt-1.5 text-xs text-muted">
            Records, not findings; document type is shown with each item.
          </p>
        </Facts>
        <Facts
          icon="package"
          title="Manufacturer product labels"
          accent="border-l-4 border-l-ev-manufacturer"
          present={t.labels > 0}
          none="No NIH DSLD label matched this plant. This is a coverage statement, not a safety statement."
        >
          <p>
            {row.dsld_products.toLocaleString()} DSLD products list this plant by a resolved
            ingredient name.
          </p>
          <p className="mt-1.5 text-xs font-medium text-clay-700">
            Manufacturer information, not clinical evidence.
          </p>
        </Facts>
      </div>
      <p className="text-xs leading-relaxed text-muted">
        Supplementary research sources with a taxon mapping:{' '}
        {supplementary.length > 0
          ? supplementary
              .map(([code, status]) => `${names[code] ?? code} (${status})`)
              .join(', ')
          : 'none'}
        . These are context only and never decide an interaction class; a candidate mapping is not
        treated as a match.
      </p>
    </section>
  )
}

interface MatrixRow {
  group: string
  swatch: string
  source: string
  plants: number
  note: string
}

/** Headline coverage counts and the per-source matrix, all computed from the stored rows. */
export function CoverageSummary({ rows }: { rows: TaxonCoverage[] }) {
  const total = rows.length
  const count = (test: (row: TaxonCoverage) => boolean) => rows.filter(test).length
  const supplementary = (code: string, status: 'resolved' | 'candidate') =>
    count((r) => r.supplementary_sources[code] === status)

  const withRegulatory = count((r) => coverageTotals(r).regulatory > 0)
  const withLiterature = count((r) => coverageTotals(r).literature > 0)
  const withLabels = count((r) => r.dsld_products > 0)

  const matrix: MatrixRow[] = [
    {
      group: 'Taxonomy',
      swatch: 'bg-forest-500',
      source: 'World Flora Online accepted species',
      plants: count((r) => r.taxonomic_status === 'accepted'),
      note: 'Identity only; not evidence.',
    },
    {
      group: 'Regulatory',
      swatch: 'bg-ev-regulatory',
      source: 'EMA HMPC monographs',
      plants: count((r) => r.monograph_documents > 0),
      note: 'Official monograph documents.',
    },
    {
      group: 'Regulatory',
      swatch: 'bg-ev-regulatory',
      source: 'NCCIH fact sheets',
      plants: count((r) => r.fact_sheet_items > 0),
      note: 'Government summaries, not exhaustive evidence.',
    },
    {
      group: 'Regulatory',
      swatch: 'bg-ev-regulatory',
      source: 'openFDA drug labels naming the herb',
      plants: count((r) => r.drug_label_mentions > 0),
      note: 'Labels of medications that mention the herb.',
    },
    {
      group: 'Literature',
      swatch: 'bg-ev-clinical',
      source: 'PubMed, clinical-evidence search',
      plants: count((r) => r.literature_clinical_items > 0),
      note: 'Records, by document type; not a quality rating.',
    },
    {
      group: 'Literature',
      swatch: 'bg-ev-clinical',
      source: 'PubMed, interaction search',
      plants: count((r) => r.literature_interaction_items > 0),
      note: 'Records, by document type; not a quality rating.',
    },
    ...(['ddid', 'supp_ai', 'livertox'] as const).map((code) => ({
      group: 'Supplementary',
      swatch: 'bg-ev-supplementary',
      source: { ddid: 'DDID experimental records', supp_ai: 'Supp.AI mentions', livertox: 'LiverTox' }[
        code
      ],
      plants: supplementary(code, 'resolved'),
      note: `Resolved mappings${
        supplementary(code, 'candidate') > 0
          ? `; ${supplementary(code, 'candidate')} further plant(s) have only a candidate mapping, which is not used as a match`
          : ''
      }. Context only.`,
    })),
    {
      group: 'Manufacturer labels',
      swatch: 'bg-ev-manufacturer',
      source: 'NIH DSLD product labels',
      plants: withLabels,
      note: 'Not clinical evidence; never used for classification.',
    },
  ]

  const tiles = [
    { label: 'Plants in the index', value: total, hint: 'Accepted WFO species', swatch: 'bg-forest-500' },
    { label: 'With regulatory material', value: withRegulatory, hint: 'EMA, NCCIH or openFDA', swatch: 'bg-ev-regulatory' },
    { label: 'With indexed literature', value: withLiterature, hint: 'PubMed records', swatch: 'bg-ev-clinical' },
    { label: 'With product labels', value: withLabels, hint: 'NIH DSLD · not evidence', swatch: 'bg-ev-manufacturer' },
  ]

  return (
    <section aria-label="Dataset coverage" className="space-y-3">
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((tile) => (
          <li key={tile.label} className="rounded-xl border border-line bg-surface p-4 shadow-soft">
            <p className="flex items-center gap-2 text-xs font-medium text-muted">
              <span aria-hidden="true" className={`h-2 w-2 rounded-full ${tile.swatch}`} />
              {tile.label}
            </p>
            <p className="mt-1 font-display text-3xl font-semibold text-forest-950">
              {tile.value}
              <span className="ml-1 text-base font-normal text-muted">/ {total}</span>
            </p>
            <p className="text-xs text-muted">{tile.hint}</p>
          </li>
        ))}
      </ul>
      <Disclosure title="Coverage by source">
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <caption className="sr-only">Number of plants covered by each source</caption>
            <thead className="text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Kind
                </th>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Source
                </th>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Plants
                </th>
                <th scope="col" className="py-2 font-semibold">
                  What it means
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {matrix.map((row) => (
                <tr key={row.source}>
                  <td className="py-2 pr-3 text-ink-soft">
                    <span className="inline-flex items-center gap-2">
                      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${row.swatch}`} />
                      {row.group}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-medium text-ink">{row.source}</td>
                  <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-ink">
                    {row.plants} / {total}
                  </td>
                  <td className="py-2 text-xs text-muted">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-muted">
          Counts come from the stored records for these {total} plants. Different sources cover
          different plants, and a count of records is not a measure of evidence strength.
        </p>
      </Disclosure>
    </section>
  )
}
