/**
 * Presentation metadata for registered sources: how each is categorised, what kind of data it
 * is, what limits its use, and the licence qualifications as the registry records them. This is
 * descriptive text only. Licence status, redistribution flag, URLs and retrieval dates always
 * come from the backend registry. Nothing here upgrades a licence: where the registry says "to
 * verify", this file says so too. An unknown source code is shown under "Other registered
 * sources" rather than being guessed.
 */
export type SourceCategory =
  | 'regulatory'
  | 'literature'
  | 'supplementary'
  | 'manufacturer'
  | 'reference'
  | 'internal'
  | 'other'

/** Restrictions that go beyond the registry's boolean `redistributable` flag. */
export type SourceRestriction = 'permission_required' | 'local_only'

export interface SourceMeta {
  category: SourceCategory
  dataType: string
  role: string
  limitation: string
  restriction?: SourceRestriction
  /** Attribution requirement exactly as far as the recorded licence text states one. */
  attribution?: string
  /** Licence qualifications and unresolved questions, taken from the recorded licence text. */
  licenceNotes: string[]
}

export const PRODUCT_LABEL_NOTICE =
  'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.'

export const SOURCE_META: Record<string, SourceMeta> = {
  ema_hmpc: {
    category: 'regulatory',
    dataType: 'Herbal monographs',
    role: 'Indications, use categories and interaction statements. Statements here can determine an interaction class.',
    limitation:
      'Monographs cover a finite set of plants and carry a date. A monograph that reports no interaction is the source’s statement, not proof of safety.',
    attribution: 'Acknowledgement of the source is part of the recorded qualification.',
    licenceNotes: [
      'Recorded as: reproduction authorised with acknowledgement of the source. The registry marks this “to verify”.',
      'HerbaGuard does not treat EMA content as freely redistributable until the terms are verified.',
    ],
  },
  nccih: {
    category: 'regulatory',
    dataType: 'Government fact sheets',
    role: 'Plain-language safety and interaction statements for widely used herbs.',
    limitation:
      'Fact sheets are government summaries, not exhaustive clinical evidence, and may name a drug only as an example.',
    licenceNotes: [
      'Recorded as U.S. government work (public domain); the page notices still need to be verified.',
      'The registry marks the licence “to verify”, so it is not treated as verified.',
    ],
  },
  openfda_label: {
    category: 'regulatory',
    dataType: 'Drug-label interaction sections',
    role: 'What the medication’s own label says about herbal products.',
    limitation:
      'Labels name botanicals mostly as examples. Wording varies by manufacturer and label date.',
    licenceNotes: [
      'Recorded as the openFDA licence (CC0) with the registry caveat “to verify”.',
      'The CC0 qualification is shown as recorded; it has not been verified.',
    ],
  },
  fda_cyp_table: {
    category: 'regulatory',
    dataType: 'Enzyme and transporter substrate table',
    role: 'Mechanism context: which drugs are substrates of an enzyme or transporter.',
    limitation:
      'Gives mechanism context only. It is not proof of an interaction in humans.',
    licenceNotes: [
      'Recorded as U.S. government work (public domain); the page notices still need to be verified.',
      'The registry marks the licence “to verify”, so it is not treated as verified.',
    ],
  },
  pubmed: {
    category: 'literature',
    dataType: 'Publication records and abstracts',
    role: 'Indexed studies and reviews, grouped by document type.',
    limitation:
      'A document type describes a design. HerbaGuard does not pool studies or rate their quality.',
    restriction: 'local_only',
    licenceNotes: [
      'Bibliographic metadata is recorded as free to use.',
      'Abstracts are copyrighted by their publishers. They are kept in the local store only and are not redistributed.',
    ],
  },
  livertox: {
    category: 'supplementary',
    dataType: 'Hepatotoxicity reviews',
    role: 'Context for questions about liver injury.',
    limitation:
      'The likelihood score is not an interaction class, and a missing liver entry is not evidence of liver safety.',
    attribution: 'Acknowledgement of NIDDK / LiverTox is requested.',
    licenceNotes: [
      'Verified: copyright free (NIDDK), with acknowledgement requested.',
      'The download’s terms of use treat documents without a licence statement as public domain; none of the chapters has one.',
    ],
  },
  ddid: {
    category: 'supplementary',
    dataType: 'Experimental interaction records',
    role: 'Species, design and result of individual experiments, shown as context.',
    limitation:
      'A secondary database. Its own labels are not HerbaGuard classes, and one study is not a confirmed clinical interaction.',
    licenceNotes: [
      'The downloaded files do not state a licence, and their terms of use have not been verified.',
      'No redistribution permission is implied.',
    ],
  },
  supp_ai: {
    category: 'supplementary',
    dataType: 'Machine-extracted literature mentions',
    role: 'Sentences from papers that mention a herb and a drug together, shown as supplementary context.',
    limitation:
      'Extracted automatically and unconfirmed: mentions are supplementary context, not confirmed interactions. They never decide a class and never support a “no interaction” conclusion. Animal and in-vitro mentions are labelled as such.',
    restriction: 'permission_required',
    licenceNotes: [
      'The dataset is described as public and available for download, © AI2, All Rights Reserved. AI2’s terms forbid redistribution without written permission (checked 2026-11-07).',
      'No dataset licence was found. Being publicly downloadable is not permission to reuse or redistribute it.',
      'Used for local research only.',
    ],
  },
  nih_dsld: {
    category: 'manufacturer',
    dataType: 'Dietary-supplement product labels',
    role: 'What manufacturers print on products that list a plant as an ingredient.',
    limitation: `${PRODUCT_LABEL_NOTICE} Never used for A–E classification.`,
    licenceNotes: [
      PRODUCT_LABEL_NOTICE,
      'Licence unverified and not redistributable: the DSLD and ODS sites refused automated access (HTTP 403, 2026-11-07), so the terms were not confirmed.',
      'Manufacturer label content is not used for A–E classification.',
    ],
  },
  rxnav: {
    category: 'reference',
    dataType: 'Drug terminology (RxNorm)',
    role: 'Resolves medication names to standard identifiers.',
    limitation: 'Contains no herb–drug evidence.',
    licenceNotes: [
      'Catalogue-level licence recorded: free from the U.S. National Library of Medicine.',
      'ATC codes are owned by the WHO Collaborating Centre; only the codes are stored.',
    ],
  },
  wfo: {
    category: 'reference',
    dataType: 'Plant taxonomy (World Flora Online)',
    role: 'Accepted names and identifiers for every plant in the index.',
    limitation: 'Establishes identity only. A taxonomic record is not evidence.',
    licenceNotes: [
      'Catalogue-level licence recorded (CC0). Review the source terms before reuse.',
    ],
  },
  wfo_ethcstwin: {
    category: 'reference',
    dataType: 'Plant taxonomy (WFO backbone download)',
    role: 'Cross-references from the WFO backbone for each plant.',
    limitation: 'Establishes identity only. A taxonomic record is not evidence.',
    licenceNotes: [
      'Catalogue-level licence recorded (CC0, WFO backbone). Review the source terms before reuse.',
    ],
  },
  wikidata: {
    category: 'reference',
    dataType: 'Cross-reference identifiers',
    role: 'Links plants to identifiers in other databases.',
    limitation: 'Identifiers only; contains no evidence used by HerbaGuard.',
    licenceNotes: ['Catalogue-level licence recorded (CC0). Review the source terms before reuse.'],
  },
  gbif: {
    category: 'reference',
    dataType: 'Backbone taxonomy (GBIF)',
    role: 'Cross-references and name checks for each plant.',
    limitation: 'Establishes identity only. A taxonomic record is not evidence.',
    attribution:
      'CC BY 4.0 would require attribution; the recorded licence is marked “to verify”.',
    licenceNotes: [
      'Recorded as the GBIF Backbone Taxonomy under CC BY 4.0, with the registry caveat “to verify”.',
      'Not treated as verified.',
    ],
  },
  wcvp_ethcstwin: {
    category: 'reference',
    dataType: 'Plant taxonomy (WCVP download)',
    role: 'Cross-references and native-range information.',
    limitation: 'Establishes identity and range only. A taxonomic record is not evidence.',
    licenceNotes: [
      'The WCVP download licence is recorded as “to verify”.',
      'No redistribution permission is assumed.',
    ],
  },
  taxtree_ethcstwin: {
    category: 'reference',
    dataType: 'Taxonomy (NCBI Taxonomy)',
    role: 'Taxonomy identifiers for each plant.',
    limitation: 'Establishes identity only. A taxonomic record is not evidence.',
    licenceNotes: [
      'Catalogue-level licence recorded: public, per NCBI policies. Review those policies before reuse.',
    ],
  },
  herbaguard_curated: {
    category: 'internal',
    dataType: 'Project-curated tables',
    role: 'Curated scope, name overrides and other tables maintained in the HerbaGuard repository.',
    limitation: 'Reflects the project’s own curation decisions, not an external source.',
    licenceNotes: ['Verified: the project’s own tables, under the project licence (MIT).'],
  },
  herbaguard_ai_index: {
    category: 'internal',
    dataType: 'Derived search index',
    role: 'Search segments built from stored evidence for retrieval.',
    limitation: 'Derived from other sources and adds no evidence of its own.',
    licenceNotes: [
      'Each segment keeps the licence of the source document it came from; this entry grants no additional rights.',
    ],
  },
}

export const SOURCE_CATEGORIES: {
  key: SourceCategory
  title: string
  summary: string
  swatch: string
}[] = [
  {
    key: 'regulatory',
    title: 'Regulatory & government evidence',
    summary: 'Official statements, quoted verbatim. These can determine an interaction class.',
    swatch: 'bg-ev-regulatory',
  },
  {
    key: 'literature',
    title: 'Clinical & scientific literature',
    summary: 'Indexed publications, shown by document type rather than by a quality score.',
    swatch: 'bg-ev-clinical',
  },
  {
    key: 'supplementary',
    title: 'Supplementary research material',
    summary: 'Context only. It never decides a class and is never presented as proof.',
    swatch: 'bg-ev-supplementary',
  },
  {
    key: 'manufacturer',
    title: 'Manufacturer product-label information',
    summary: 'Describes products, not study findings. Never clinical evidence.',
    swatch: 'bg-ev-manufacturer',
  },
  {
    key: 'reference',
    title: 'Reference data (taxonomy and terminology)',
    summary: 'Used to identify plants and medications. Contains no herb–drug evidence.',
    swatch: 'bg-class-e',
  },
  {
    key: 'internal',
    title: 'HerbaGuard internal data',
    summary: 'Project-curated tables and the derived search index.',
    swatch: 'bg-forest-500',
  },
  {
    key: 'other',
    title: 'Other registered sources',
    summary: 'Registered in this instance without presentation metadata in this interface.',
    swatch: 'bg-class-e',
  },
]

export function sourceMeta(code: string): SourceMeta {
  return (
    SOURCE_META[code] ?? {
      category: 'other',
      dataType: 'Not described in this interface',
      role: 'Registered in the backend source registry.',
      limitation: 'Check the provider’s terms before relying on or reusing this source.',
      licenceNotes: ['No licence qualifications are described in this interface for this source.'],
    }
  )
}
