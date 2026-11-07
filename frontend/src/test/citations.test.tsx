import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../App'
import { CitationCard } from '../components/CitationCard'
import {
  documentType,
  evidenceCategory,
  licenceStatusPlain,
  qualifierDetails,
  recordType,
  studyContext,
} from '../lib/citations'
import { licenceLabel, sourceLabel } from '../lib/format'
import type { AskResponse, Citation, EvidenceTypeInfo, Provenance, SourceRow } from '../lib/types'
import { ASK_RESPONSE, META } from './fixtures'
import { mockFetch, renderWithProviders } from './render'

const BASE_ROUTES = {
  '/api/v1/meta': [200, META] as [number, unknown],
  '/api/v1/health/ready': [200, { status: 'ok', checks: [] }] as [number, unknown],
}

const NOTE = 'It is not a quality rating.'
const type = (code: string, label: string): EvidenceTypeInfo => ({
  code,
  label,
  basis: 'source_document',
  quality_assessed: false,
  note: NOTE,
})

const provenance = (overrides: Partial<Provenance>): Provenance => ({
  source_code: 'ddid',
  source_name: 'DDID — Drug–Diet (herb and food) Interaction Database',
  licence: 'Not stated in the downloaded files; terms of use not yet verified',
  licence_status: 'to_verify',
  retrieved_url: 'https://example.org/ddid.csv',
  retrieved_at: '2026-11-06T21:11:26Z',
  source_version: null,
  extraction_method: 'ddid_csv_v1',
  location: 'Interaction Information.csv, row(s) 10420',
  excerpt: null,
  ...overrides,
})

const DDID_TEXT =
  "DDID record: Hypericum perforatum with Warfarin. Species: Homo Sapiens. design: Randomized, open, crossover; n: 12; drug dose: 25 mg; dosage form: Tablet; herb/food dose: 3 g/day; timing: Administration after 21 days of pretreatment; method: INR,HPLC; sample: Blood, Urine. Result: INR was not affected. Conclusion: clearance was induced. DDID label: Negative."

const base: Citation = {
  label: 'X2',
  kind: 'observation',
  role: 'experimental_evidence',
  evidence_item_id: 'ev-x2',
  external_id: 'ddid:PMID:15089812',
  source_code: 'ddid',
  evidence_type: type('CLIN', 'Other clinical study'),
  title: "Effect of St John's wort and ginseng on warfarin in healthy subjects",
  url: 'https://pubmed.ncbi.nlm.nih.gov/15089812/',
  location: 'Interaction Information.csv, row(s) 10420',
  excerpt: DDID_TEXT,
  qualifiers: [
    'study context: human study (as stated by the dataset); a single study, not a confirmed clinical interaction',
    "dataset label 'Negative' is the database's own label, not a HerbaGuard A-E class",
    'secondary database record; licence of the dataset not verified',
  ],
  provenance: [provenance({})],
}

const DDID = base
const REGULATORY: Citation = {
  label: 'S4',
  kind: 'statement',
  role: 'direct_evidence',
  evidence_item_id: 'ev-s4',
  external_id: 'setid#drug_interactions',
  source_code: 'openfda_label',
  evidence_type: type('REG', 'Regulatory document'),
  title: 'FDA label: Warfarin Sodium — drug interactions',
  url: 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=7c4d',
  location: 'section drug_interactions',
  excerpt: 'Some botanicals may decrease the effects of warfarin sodium.',
  qualifiers: [
    'statement type: interaction (The source states an interaction, contraindication or effect.)',
    'about: warfarin (drug)',
    'subject check: the sentence names the label’s drug',
  ],
  provenance: [
    provenance({
      source_code: 'openfda_label',
      source_name: 'openFDA drug labels (SPL)',
      licence: 'openFDA licence (CC0, to verify)',
      location: 'section drug_interactions',
    }),
  ],
}
const INCOMPLETE: Citation = {
  label: 'F1',
  kind: 'fact',
  role: 'catalogue',
  evidence_item_id: null,
  external_id: null,
  source_code: null,
  evidence_type: null,
  title: null,
  url: null,
  location: null,
  excerpt: 'HerbaGuard holds 2 records for this herb.',
  qualifiers: [],
  provenance: [],
}
const CLASSIFICATION: Citation = {
  label: 'C1',
  kind: 'classification',
  role: 'deterministic_classification',
  evidence_item_id: null,
  external_id: null,
  source_code: null,
  evidence_type: null,
  title: null,
  url: null,
  location: null,
  excerpt: 'Pair: St John’s wort + warfarin\nClass A — Documented',
  qualifiers: ['deterministic rules v1; no machine learning or LLM'],
  provenance: [],
}
const PUBMED: Citation = {
  label: 'E2',
  kind: 'excerpt',
  role: 'direct_evidence',
  evidence_item_id: 'ev-e2',
  external_id: '31937153',
  source_code: 'pubmed',
  evidence_type: type('SR', 'Systematic review or meta-analysis'),
  title: 'Effect of ginger in the treatment of nausea: a meta-analysis.',
  url: 'https://pubmed.ncbi.nlm.nih.gov/31937153/',
  location: 'title_abstract, characters 0–1003',
  excerpt: 'Nausea and vomiting affect up to 85% of pregnant women.',
  qualifiers: [
    'retrieved passage (rank 2); retrieval rank is not evidence quality',
    'publication year: 2022',
    'linked herbs: Zingiberis rhizoma',
  ],
  provenance: [
    provenance({
      source_code: 'pubmed',
      source_name: 'PubMed via NCBI E-utilities',
      licence: 'Metadata free; abstracts publisher-copyrighted (local store only)',
    }),
  ],
}

const row = (code: string, overrides: Partial<SourceRow> = {}): SourceRow => ({
  code,
  name: code,
  provider: 'Provider',
  homepage_url: null,
  is_official: true,
  licence: null,
  licence_status: 'to_verify',
  redistributable: false,
  last_run_status: null,
  last_run_finished_at: null,
  records: 1,
  ...overrides,
})

const REGISTRY: SourceRow[] = [
  row('ddid', { name: 'DDID', provider: 'Guangzhou Normal University' }),
  row('openfda_label', {
    provider: 'U.S. Food and Drug Administration',
    redistributable: true,
  }),
  row('supp_ai', { provider: 'Allen Institute for AI' }),
  row('livertox', { provider: 'NIDDK', licence_status: 'verified', redistributable: true }),
  row('rxnav', { provider: 'U.S. National Library of Medicine', licence_status: 'catalogue' }),
]

function renderCard(citation: Citation, registry: SourceRow[] = REGISTRY) {
  mockFetch({ '/api/v1/sources': [200, registry] })
  return renderWithProviders(
    <ol>
      <CitationCard citation={citation} />
    </ol>,
  )
}

async function openMore(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText('More about this citation'))
}

/** The badge labels of a citation, in order: only buttons that carry a tooltip. */
const pills = (card: HTMLElement) =>
  within(card)
    .getAllByRole('button')
    .filter((button) => button.hasAttribute('aria-describedby'))
    .map((button) => button.textContent?.trim())

const tip = (name: string | RegExp, description?: string | RegExp) =>
  screen.getByRole('button', { name, ...(description ? { description } : {}) })

describe('citation reference and answer links', () => {
  it('shows the reference id as a label with its meaning in a tooltip', async () => {
    renderCard(DDID)
    const card = (await screen.findByRole('button', { name: 'X2' })).closest('li') as HTMLElement
    expect(card).toHaveAttribute('id', 'citation-X2')
    expect(tip('X2', /not an evidence-quality rating/)).toBeInTheDocument()
  })

  it('links each statement in the answer to its citation and names the record type', async () => {
    const response: AskResponse = {
      ...ASK_RESPONSE,
      paragraphs: [
        { text: 'A study found induced clearance.', citations: ['X2'] },
        { text: 'The label lists botanicals.', citations: ['S4', 'C1'] },
      ],
      citations: [DDID, REGULATORY, CLASSIFICATION],
    }
    mockFetch({ ...BASE_ROUTES, 'POST /api/v1/ai/ask': [200, response] })
    const user = userEvent.setup()
    renderWithProviders(<AppRoutes />, { route: '/assistant' })
    await user.type(screen.getByLabelText('Your question'), 'Question')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(
      await screen.findByRole('link', {
        name: 'Reference X2: Experimental record. Opens the source record below.',
      }),
    ).toHaveAttribute('href', '#citation-X2')
    expect(
      screen.getByRole('link', {
        name: 'Reference S4: Source statement. Opens the source record below.',
      }),
    ).toHaveAttribute('href', '#citation-S4')
    expect(
      screen.getByRole('link', {
        name: 'Reference C1: HerbaGuard classification. Opens the source record below.',
      }),
    ).toHaveAttribute('href', '#citation-C1')
    for (const id of ['X2', 'S4', 'C1']) {
      expect(document.getElementById(`citation-${id}`)).not.toBeNull()
    }
    expect(screen.getByText(/It is a label, not an evidence-quality rating/)).toBeInTheDocument()
  })
})

describe('compact citations: labels visible, explanations on demand', () => {
  it('keeps the labels visible and the explanations out of the page until interaction', async () => {
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    for (const label of [
      'Experimental record',
      'Experimental evidence',
      'Other clinical study',
      'DDID experimental records',
      'Licence unverified',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeVisible()
    }
    // no visible bubble and no explanatory paragraph: the text exists only as an accessible
    // description, which assistive technology reads without any hover
    expect(document.querySelector('[data-tooltip-bubble]')).toBeNull()
    const explanation = screen.getByText(/does not automatically indicate a human clinical study/)
    expect(explanation.className).toContain('sr-only')
    expect(screen.getByText('More about this citation').closest('details')).not.toHaveAttribute(
      'open',
    )
  })

  it('explains each visible label of an experimental record without upgrading it', async () => {
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    tip(
      'Experimental record',
      'A database record describing findings from an experimental study. It does not automatically indicate a human clinical study.',
    )
    tip(
      'Experimental evidence',
      'Evidence classified as experimental. This label alone does not establish clinical effectiveness or certainty.',
    )
    tip('Other clinical study', /not its quality or certainty/)
    tip(
      'DDID experimental records',
      /The source of this record: DDID — Drug–Diet \(herb and food\) Interaction Database\. Experimental interaction records\./,
    )
    tip(
      'Licence unverified',
      'The source’s redistribution permissions have not been verified. This does not imply permission to redistribute.',
    )
    // nothing claims human clinical evidence or quality
    expect(evidenceCategory(DDID).description).not.toMatch(/proven|confirmed effect|high quality/i)
  })

  it('shows each label with the matching explanation for every record type and category', () => {
    for (const [kind, label] of [
      ['classification', 'HerbaGuard classification'],
      ['statement', 'Source statement'],
      ['mechanism', 'Mechanism relationship'],
      ['excerpt', 'Retrieved passage'],
      ['fact', 'Catalogue fact'],
      ['observation', 'Experimental record'],
      ['hepatotoxicity', 'Liver-injury record'],
      ['mention', 'Literature mention'],
      ['product_label', 'Manufacturer product label'],
    ] as const) {
      const described = recordType({ ...DDID, kind })
      expect(described.label).toBe(label)
      expect(described.description.length).toBeGreaterThan(20)
    }
    for (const [role, label, text] of [
      ['direct_evidence', 'Direct evidence', /does not establish certainty/],
      ['graph_context', 'Mechanism context', /not proof of an interaction in people/],
      ['experimental_evidence', 'Experimental evidence', /does not establish clinical effectiveness/],
      ['supplementary_mention', 'Supplementary mention', /Not a confirmed interaction|not a confirmed interaction/],
      ['hepatotoxicity_evidence', 'Liver-injury evidence', /not evidence of liver safety/],
      ['product_label_information', 'Product-label information', /not clinical evidence/],
    ] as const) {
      const described = evidenceCategory({ ...REGULATORY, role })
      expect(described.label).toBe(label)
      expect(described.description).toMatch(text)
    }
  })

  it('describes document types as kinds of document, never as quality', () => {
    for (const [code, label] of [
      ['REG', 'Regulatory document'],
      ['GOV', 'Government summary'],
      ['SR', 'Systematic review'],
      ['ANIMAL', 'Animal study'],
    ]) {
      expect(documentType(type(code, label))?.description).toMatch(/not its quality or certainty/)
    }
    expect(documentType(type('ANIMAL', 'Animal study'))?.description).toMatch(
      /does not show an effect in people/,
    )
    expect(documentType(null)).toBeNull()
  })
})

describe('source, provenance and recorded details', () => {
  it('shows the source label with the registered name, kind and provider in its tooltip', async () => {
    renderCard(REGULATORY)
    await screen.findByRole('button', { name: 'S4' })
    await waitFor(() =>
      tip(
        'openFDA drug labels',
        /The source of this record: openFDA drug labels \(SPL\)\. Drug-label interaction sections\. Provided by U\.S\. Food and Drug Administration\./,
      ),
    )
    expect(
      screen.getByRole('link', { name: /FDA label: Warfarin Sodium — drug interactions/ }),
    ).toHaveAttribute('href', 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=7c4d')
  })

  it('keeps the provenance, recorded details and notes in the collapsed panel', async () => {
    const user = userEvent.setup()
    renderCard(PUBMED)
    await screen.findByRole('button', { name: 'E2' })
    // the document type is a visible label with its explanation on demand
    tip('Systematic review or meta-analysis', /combines the results of other studies/)

    await openMore(user)
    const recorded = screen.getByRole('region', { name: 'Recorded details' })
    expect(within(recorded).getByText('Publication year')).toBeInTheDocument()
    expect(within(recorded).getByText('2022')).toBeInTheDocument()
    expect(within(recorded).getByText('Linked herbs')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Notes' })).toHaveTextContent(
      'retrieval rank is not evidence quality',
    )
    await user.click(screen.getByText(/Source provenance \(1\)/))
    // the exact registered source name is kept in the provenance
    expect(
      screen.getAllByText('PubMed via NCBI E-utilities', { exact: false }).length,
    ).toBeGreaterThanOrEqual(2) // the source tooltip and the provenance entry
    expect(screen.getByRole('link', { name: /example\.org\/ddid\.csv/ })).toBeInTheDocument()
  })

  it('splits qualifiers into labelled fields and plain notes without inventing any', () => {
    const { fields, notes } = qualifierDetails(REGULATORY.qualifiers)
    expect(fields.map((f) => f.label)).toEqual(['Statement type', 'About'])
    expect(notes).toEqual(['subject check: the sentence names the label’s drug'])
    expect(qualifierDetails([])).toEqual({ fields: [], notes: [] })
  })
})

describe('study context', () => {
  it('shows only the fields present in an experimental record', async () => {
    const user = userEvent.setup()
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    await openMore(user)
    const study = screen.getByRole('region', { name: 'Study context' })
    const value = (label: string) =>
      within(study).getByText(label).closest('div')?.querySelector('dd')?.textContent
    expect(value('Species')).toBe('Homo Sapiens')
    expect(value('Study design')).toBe('Randomized, open, crossover')
    expect(value('Sample size')).toBe('12')
    expect(value('Duration or timing')).toBe('Administration after 21 days of pretreatment')
    expect(value('Methods')).toBe('INR,HPLC')
    expect(value('Herb dose')).toBe('3 g/day')
    expect(value('Drug dose')).toBe('25 mg')
    expect(value('Sample tested')).toBe('Blood, Urine')
    expect(within(study).getByText(/nothing here is inferred/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Recorded details' })).toHaveTextContent(
      'human study (as stated by the dataset)',
    )
  })

  it('omits fields that are missing and never turns "not stated" into a value', () => {
    const fields = studyContext({
      ...DDID,
      excerpt:
        'DDID record: Hypericum perforatum with Warfarin. Species: not stated. design: Case Report; n: 1. Result: bleeding. Conclusion: not stated. DDID label: Harmful.',
    })
    expect(fields).toEqual([
      { label: 'Species', value: 'Not stated in the record' },
      { label: 'Study design', value: 'Case Report' },
      { label: 'Sample size', value: '1' },
    ])
  })

  it('reports that no study details could be read instead of guessing', async () => {
    const user = userEvent.setup()
    renderCard({ ...DDID, excerpt: 'An experimental record with no recognisable fields.' })
    await screen.findByRole('button', { name: 'X2' })
    await openMore(user)
    expect(
      screen.getByText(/No study details \(species, design, sample size, duration or methods\)/),
    ).toBeInTheDocument()
    expect(studyContext({ ...DDID, excerpt: 'unstructured' })).toEqual([])
  })

  it('does not show study context for other kinds of record', async () => {
    const user = userEvent.setup()
    renderCard(REGULATORY)
    await screen.findByRole('button', { name: 'S4' })
    await openMore(user)
    expect(screen.queryByRole('region', { name: 'Study context' })).not.toBeInTheDocument()
    expect(studyContext(REGULATORY)).toEqual([])
  })
})

describe('missing optional metadata', () => {
  it('renders an item with almost no metadata without inventing any', async () => {
    renderCard(INCOMPLETE)
    await screen.findByRole('button', { name: 'F1' })
    expect(screen.getByText('Untitled source')).toBeInTheDocument()
    tip('Catalogue fact', /not a study finding/)
    tip('Not recorded', 'No source is recorded for this item.')
    // only the labels the citation supports: no document type and no licence badge
    const card = screen.getByRole('button', { name: 'F1' }).closest('li') as HTMLElement
    expect(pills(card)).toEqual(['F1', 'Catalogue fact', 'Catalogue fact', 'Not recorded'])
    expect(screen.getByText(/HerbaGuard holds 2 records/)).toBeInTheDocument()

    const user = userEvent.setup()
    await openMore(user)
    expect(screen.queryByRole('region', { name: 'Recorded details' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Licence as recorded' })).not.toBeInTheDocument()
  })

  it('shows the classification as compact labels, never as an external source', async () => {
    renderCard(CLASSIFICATION)
    await screen.findByRole('button', { name: 'C1' })
    tip('C1', /Reference ID/)
    tip(
      'HerbaGuard classification',
      'The interaction class computed by HerbaGuard’s fixed rules from stored statements. This is a result, not a source document.',
    )
    tip('Deterministic classification', 'Computed by fixed rules, not by the language model.')
    tip(
      'HerbaGuard rules',
      'Computed by HerbaGuard’s fixed rules. There is no external source document behind this item.',
    )
    const card = screen.getByRole('button', { name: 'C1' }).closest('li') as HTMLElement
    expect(pills(card)).toEqual([
      'C1',
      'HerbaGuard classification',
      'Deterministic classification',
      'HerbaGuard rules',
    ])
    expect(screen.queryByRole('link')).not.toBeInTheDocument() // no link to a source document
  })

  it('keeps the full classification result in the expandable details, unchanged', async () => {
    const user = userEvent.setup()
    renderCard(CLASSIFICATION)
    await screen.findByRole('button', { name: 'C1' })
    const card = screen.getByRole('button', { name: 'C1' }).closest('li') as HTMLElement
    const details = card.querySelector('details') as HTMLElement
    // not printed beneath the labels ...
    expect(details).toContainElement(within(card).getByText(/Class A — Documented/))
    expect(details).not.toHaveAttribute('open')
    // ... but available, exactly as returned
    await openMore(user)
    const section = screen.getByRole('region', { name: 'Classification result' })
    expect(section).toHaveTextContent('Pair: St John’s wort + warfarin')
    expect(section.querySelector('p')?.textContent).toBe(CLASSIFICATION.excerpt)
    expect(screen.getByRole('region', { name: 'Notes' })).toHaveTextContent(
      'deterministic rules v1; no machine learning or LLM',
    )
  })

  it('still renders when the source registry is unavailable', async () => {
    mockFetch({ '/api/v1/sources': [503, { error: { code: 'x', message: 'down' } }] })
    renderWithProviders(
      <ol>
        <CitationCard citation={DDID} />
      </ol>,
    )
    expect(await screen.findByRole('button', { name: 'X2' })).toBeInTheDocument()
    tip('Licence unverified', /redistribution permissions have not been verified/)
    expect(screen.queryByRole('button', { name: /Licence details/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Not redistributable' })).not.toBeInTheDocument()
  })
})

describe('licence status labels', () => {
  it('explains an unverified licence and keeps the recorded licence text', async () => {
    const user = userEvent.setup()
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    tip(
      'Licence unverified',
      'The source’s redistribution permissions have not been verified. This does not imply permission to redistribute.',
    )
    await openMore(user)
    expect(screen.getByRole('region', { name: 'Licence as recorded' })).toHaveTextContent(
      'Not stated in the downloaded files; terms of use not yet verified',
    )
  })

  it('shows the extra restriction recorded for a source that needs permission', async () => {
    renderCard({
      ...DDID,
      label: 'U1',
      kind: 'mention',
      role: 'supplementary_mention',
      source_code: 'supp_ai',
      provenance: [provenance({ source_code: 'supp_ai', source_name: 'SUPP.AI' })],
    })
    await screen.findByRole('button', { name: 'U1' })
    await waitFor(() =>
      tip(
        'Permission required',
        'Additional permission from the owner is required to redistribute it.',
      ),
    )
    tip('Licence unverified')
  })

  it('states when a source cannot be redistributed under the recorded conditions', async () => {
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    await waitFor(() =>
      tip(
        'Not redistributable',
        'The source’s content cannot be redistributed under the recorded conditions.',
      ),
    )
  })

  it('does not call an unverified source redistributable', async () => {
    renderCard(REGULATORY)
    await screen.findByRole('button', { name: 'S4' })
    await screen.findByRole('button', { name: /Licence details for/ })
    tip('Licence unverified')
    expect(screen.queryByRole('button', { name: 'Not redistributable' })).not.toBeInTheDocument()
    expect(screen.queryByText(/A verified licence is recorded/)).not.toBeInTheDocument()
  })

  it('shows a verified licence as such and opens the full licence details', async () => {
    const user = userEvent.setup()
    renderCard(
      {
        ...DDID,
        label: 'H1',
        kind: 'hepatotoxicity',
        role: 'hepatotoxicity_evidence',
        source_code: 'livertox',
        provenance: [
          provenance({
            source_code: 'livertox',
            source_name: 'LiverTox',
            licence_status: 'verified',
            licence: 'Copyright free (NIDDK); acknowledgement requested.',
          }),
        ],
      },
      [
        row('livertox', {
          name: 'LiverTox',
          provider: 'NIDDK',
          licence_status: 'verified',
          redistributable: true,
          licence: 'Copyright free (NIDDK); acknowledgement requested.',
        }),
      ],
    )
    await screen.findByRole('button', { name: 'H1' })
    tip('Licence verified', 'A verified licence is recorded for this source.')
    await user.click(await screen.findByRole('button', { name: /Licence details for LiverTox/ }))
    expect(screen.getByRole('dialog', { name: 'LiverTox' })).toHaveTextContent(
      'Acknowledgement of NIDDK / LiverTox is requested.',
    )
  })

  it('shows a catalogue licence as unverified-by-catalogue, not verified', () => {
    expect(licenceStatusPlain('catalogue')).toBe(
      'A catalogue-level licence is recorded. It has not been verified.',
    )
    expect(licenceStatusPlain('verified')).toBe('A verified licence is recorded for this source.')
  })

  it('keeps the exact manufacturer-label warning on a product-label citation', async () => {
    renderCard({
      ...DDID,
      label: 'P1',
      kind: 'product_label',
      role: 'product_label_information',
      source_code: 'nih_dsld',
      evidence_type: null,
      provenance: [
        provenance({
          source_code: 'nih_dsld',
          source_name: 'NIH Dietary Supplement Label Database (DSLD)',
          licence: 'Not in download',
        }),
      ],
    })
    await screen.findByRole('button', { name: 'P1' })
    expect(
      screen.getAllByText(
        'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
      ).length,
    ).toBeGreaterThanOrEqual(2)
  })
})

describe('layout and consistency', () => {
  it('shows the labels as one wrapping row of badges and lets long text wrap', async () => {
    renderCard(DDID)
    const chip = await screen.findByRole('button', { name: 'X2' })
    // the badges sit in one flex row that wraps on narrow screens instead of overflowing
    const row = chip.closest('div') as HTMLElement
    expect(row.className).toContain('flex-wrap')
    expect(pills(row.closest('li') as HTMLElement).slice(0, 5)).toEqual([
      'X2',
      'Experimental record',
      'Experimental evidence',
      'Other clinical study',
      'DDID experimental records',
    ])
    for (const pill of within(row).getAllByRole('button')) {
      expect(pill.className).toContain('max-w-full') // a long label cannot widen the card
    }
    const [location] = screen.getAllByText(/Interaction Information\.csv, row\(s\) 10420/, {
      selector: 'p',
    })
    expect(location.className).toContain('break-words')
  })

  it('presents cached and normally generated answers identically', async () => {
    const normal: AskResponse = {
      ...ASK_RESPONSE,
      paragraphs: [{ text: 'A study found induced clearance.', citations: ['X2', 'S4'] }],
      citations: [DDID, REGULATORY],
    }
    const cached: AskResponse = {
      ...normal,
      generation: { ...normal.generation, duration_ms: 0 },
      cache: {
        served_from_cache: true,
        generated_at: '2026-11-08T09:00:00Z',
        original_generation_ms: 175000,
        validation_status: 'passed',
      },
    }
    // React generates different element ids per render; they are not part of the presentation.
    const strip = (html: string | undefined) =>
      html?.replace(/\s(id|aria-describedby)="[^"]*:[^"]*"/g, '')
    const render = async (response: AskResponse) => {
      mockFetch({ ...BASE_ROUTES, 'POST /api/v1/ai/ask': [200, response] })
      const user = userEvent.setup()
      const view = renderWithProviders(<AppRoutes />, { route: '/assistant' })
      await user.type(screen.getByLabelText('Your question'), 'Question')
      await user.click(screen.getByRole('button', { name: 'Ask' }))
      const citations = await screen.findByRole('region', { name: 'Citations' })
      await within(citations).findByRole('button', { name: 'DDID experimental records' })
      const out = {
        citations: strip(citations.innerHTML),
        answer: strip(
          (await screen.findByRole('heading', { name: 'Answer', level: 2 })).closest('section')
            ?.innerHTML,
        ),
      }
      view.unmount()
      return out
    }
    const a = await render(normal)
    const b = await render(cached)
    expect(b.citations).toBe(a.citations)
    expect(b.answer).toBe(a.answer)
  })

  it('shows no timing, token or generation diagnostics in a citation', async () => {
    const user = userEvent.setup()
    renderCard(DDID)
    await screen.findByRole('button', { name: 'X2' })
    await openMore(user)
    const card = screen.getByRole('button', { name: 'X2' }).closest('li') as HTMLElement
    expect(card).not.toHaveTextContent(/elapsed|tokens?|pipeline|generation|_ms\b/i)
  })
})

const RICH_REGISTRY: SourceRow[] = [
  row('ddid', { provider: 'Guangzhou Normal University' }),
  row('ema_hmpc', { provider: 'European Medicines Agency' }),
  row('nccih', { provider: 'U.S. National Center for Complementary and Integrative Health' }),
  row('openfda_label', { provider: 'U.S. Food and Drug Administration', redistributable: true }),
  row('pubmed', { provider: 'U.S. National Library of Medicine' }),
  row('livertox', { provider: 'NIDDK', licence_status: 'verified', redistributable: true }),
  row('supp_ai', { provider: 'Allen Institute for AI' }),
  row('nih_dsld', { provider: 'NIH Office of Dietary Supplements' }),
]

const named = (code: string, name: string, licence: string): Provenance[] => [
  provenance({ source_code: code, source_name: name, licence }),
]

const ALL_TYPES: [string, Citation][] = [
  ['HerbaGuard classification', CLASSIFICATION],
  ['DDID experimental record', DDID],
  ['openFDA label statement', REGULATORY],
  ['PubMed passage', PUBMED],
  [
    'NCCIH statement',
    {
      ...REGULATORY,
      label: 'S3',
      source_code: 'nccih',
      evidence_type: type('GOV', 'Government summary'),
      provenance: named('nccih', 'NCCIH Herbs at a Glance', 'U.S. government work (public domain)'),
    },
  ],
  [
    'EMA mechanism',
    {
      ...REGULATORY,
      label: 'M1',
      kind: 'mechanism',
      role: 'graph_context',
      source_code: 'ema_hmpc',
      provenance: named('ema_hmpc', 'EMA HMPC herbal inventory', 'Reproduction authorised (to verify)'),
    },
  ],
  [
    'EMA passage',
    {
      ...PUBMED,
      label: 'E3',
      source_code: 'ema_hmpc',
      evidence_type: type('REG', 'Regulatory document'),
      provenance: named('ema_hmpc', 'EMA HMPC herbal inventory', 'Reproduction authorised (to verify)'),
    },
  ],
  [
    'LiverTox record',
    {
      ...DDID,
      label: 'H1',
      kind: 'hepatotoxicity',
      role: 'hepatotoxicity_evidence',
      source_code: 'livertox',
      evidence_type: type('REV', 'Review'),
      excerpt: 'Likelihood score: B (likely cause of liver injury).',
      provenance: named('livertox', 'LiverTox', 'Copyright free (NIDDK)'),
    },
  ],
  [
    'Supp.AI mention',
    {
      ...DDID,
      label: 'U1',
      kind: 'mention',
      role: 'supplementary_mention',
      source_code: 'supp_ai',
      evidence_type: null,
      excerpt: 'St John’s wort reduced warfarin levels in rats.',
      provenance: named('supp_ai', 'SUPP.AI', 'AI2 terms forbid redistribution'),
    },
  ],
  [
    'NIH DSLD product label',
    {
      ...DDID,
      label: 'P1',
      kind: 'product_label',
      role: 'product_label_information',
      source_code: 'nih_dsld',
      evidence_type: null,
      excerpt: 'Consult your physician if you take anticoagulants.',
      provenance: named('nih_dsld', 'NIH Dietary Supplement Label Database (DSLD)', 'Not in download'),
    },
  ],
  ['catalogue fact with almost no metadata', INCOMPLETE],
]

describe('every citation type uses the same compact structure', () => {
  it.each(ALL_TYPES)('%s: identifier, labels and tooltips', async (_name, citation) => {
    renderCard(citation, RICH_REGISTRY)
    const chip = await screen.findByRole('button', { name: citation.label })
    const card = chip.closest('li') as HTMLElement
    expect(card).toHaveAttribute('id', `citation-${citation.label}`)
    tip(citation.label, /Reference ID/)

    // the same badge structure for every citation; only supported labels appear
    const record = recordType(citation)
    const category = evidenceCategory(citation)
    const info = documentType(citation.evidence_type)
    const expected = [citation.label, record.label, category.label]
    if (info) expected.push(info.label)
    expected.push(
      citation.source_code
        ? sourceLabel(citation.source_code)
        : citation.kind === 'classification'
          ? 'HerbaGuard rules'
          : 'Not recorded',
    )
    if (citation.provenance[0]) expected.push(licenceLabel(citation.provenance[0].licence_status))
    expect(pills(card).slice(0, expected.length)).toEqual(expected)

    // each visible label has its own accurate tooltip
    within(card).getByRole('button', { name: record.label, description: record.description })
    within(card).getByRole('button', { name: category.label, description: category.description })
    if (info) {
      within(card).getByRole('button', { name: info.label, description: info.description })
    }
    if (citation.provenance[0]) {
      within(card).getByRole('button', {
        name: licenceLabel(citation.provenance[0].licence_status),
        description: licenceStatusPlain(citation.provenance[0].licence_status),
      })
    }

    // explanations are never printed in the citation: only the hidden accessible copy exists
    for (const text of [record.description, category.description, info?.description]) {
      if (!text) continue
      for (const element of within(card).getAllByText(text)) {
        if (element.closest('[role="status"]')) continue // the mandatory label warning is shown on purpose
        expect(element.className).toContain('sr-only')
      }
    }
    expect(document.querySelector('[data-tooltip-bubble]')).toBeNull()
    expect(card.querySelector('details')).not.toHaveAttribute('open')
  })

  it.each(ALL_TYPES.filter(([, c]) => c.source_code))(
    '%s: the source label names the registered source in its tooltip and provenance',
    async (_name, citation) => {
      renderCard(citation, RICH_REGISTRY)
      const card = (await screen.findByRole('button', { name: citation.label })).closest(
        'li',
      ) as HTMLElement
      const registered = citation.provenance[0].source_name
      within(card).getByRole('button', {
        name: sourceLabel(citation.source_code as string),
        description: (text: string) => text.startsWith(`The source of this record: ${registered}.`),
      })
      const user = userEvent.setup()
      await user.click(within(card).getByText('More about this citation'))
      await user.click(within(card).getByText(/Source provenance \(1\)/))
      expect(within(card).getAllByText(registered, { exact: false }).length).toBeGreaterThan(0)
    },
  )

  it('keeps the evidence itself visible for external citations and the label warning intact', async () => {
    for (const [, citation] of ALL_TYPES) {
      if (citation.kind === 'classification') continue
      const { unmount } = renderCard(citation, RICH_REGISTRY)
      await screen.findByRole('button', { name: citation.label })
      expect(screen.getByText(`“${citation.excerpt}”`)).toBeVisible()
      if (citation.kind === 'product_label') {
        expect(
          screen.getAllByText(
            'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
          ).length,
        ).toBeGreaterThanOrEqual(1)
      }
      unmount()
    }
  })
})
