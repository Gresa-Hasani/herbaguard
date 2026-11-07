/**
 * Shown until the backend's /api/v1/meta disclaimer has loaded, so the warning is never
 * missing. Must stay identical to herbaguard.core.config.DISCLAIMER.
 */
export const FALLBACK_DISCLAIMER =
  'HerbaGuard provides information from scientific and regulatory sources. ' +
  'It is not medical advice and does not replace your doctor or pharmacist. ' +
  'The absence of a reported interaction does not mean a combination is safe.'

export interface NavItem {
  to: string
  label: string
  description: string
  icon: 'pill' | 'leaf' | 'chat' | 'home' | 'book' | 'layers'
}

/** The three workspace tools (the application experience). */
export const WORKSPACE_NAV: NavItem[] = [
  {
    to: '/interactions',
    label: 'Interaction Checker',
    description: 'Deterministic A–E classification with traceable source statements.',
    icon: 'pill',
  },
  {
    to: '/explorer',
    label: 'Herb Explorer',
    description: 'Taxonomy, regulatory information, evidence and product labels.',
    icon: 'leaf',
  },
  {
    to: '/assistant',
    label: 'Evidence Assistant',
    description: 'Answers restricted to cited, retrieved HerbaGuard evidence.',
    icon: 'chat',
  },
]

/** The public product pages (the landing experience). */
export const PUBLIC_NAV: NavItem[] = [
  { to: '/about', label: 'About', description: 'Purpose, scope and limits.', icon: 'book' },
  {
    to: '/sources',
    label: 'Sources & methodology',
    description: 'Where evidence comes from and how it is separated.',
    icon: 'layers',
  },
]

export interface InteractionClassMeta {
  letter: 'A' | 'B' | 'C' | 'D' | 'E'
  label: string
  description: string
  badge: string
  accent: string
}

/**
 * Presentation vocabulary only. The class letter always comes from the backend; this map
 * provides labels and colours and never decides a result.
 */
export const INTERACTION_CLASSES: Record<'A' | 'B' | 'C' | 'D' | 'E', InteractionClassMeta> = {
  A: {
    letter: 'A',
    label: 'Documented',
    description: 'An authoritative source states an interaction or contraindication.',
    badge: 'border-class-a/30 bg-class-a/10 text-class-a',
    accent: 'border-class-a/40 bg-class-a/5',
  },
  B: {
    letter: 'B',
    label: 'Potential',
    description: 'A class-level statement or a qualifying mechanism applies.',
    badge: 'border-class-b/30 bg-class-b/10 text-class-b',
    accent: 'border-class-b/40 bg-class-b/5',
  },
  C: {
    letter: 'C',
    label: 'Suspected / unclear',
    description: 'Only uncertain, unconfirmed or unspecific statements were found.',
    badge: 'border-class-c/30 bg-class-c/10 text-class-c',
    accent: 'border-class-c/40 bg-class-c/5',
  },
  D: {
    letter: 'D',
    label: 'No interaction evidence found',
    description: 'The sources searched contained no interaction statement. This is not safety.',
    badge: 'border-class-d/30 bg-class-d/10 text-class-d',
    accent: 'border-class-d/40 bg-class-d/5',
  },
  E: {
    letter: 'E',
    label: 'Insufficient information',
    description: 'The herb or drug could not be assessed from the available sources.',
    badge: 'border-class-e/30 bg-class-e/10 text-class-e',
    accent: 'border-class-e/40 bg-class-e/5',
  },
}

export const SOURCE_LABELS: Record<string, string> = {
  ema_hmpc: 'EMA HMPC monographs',
  nccih: 'NCCIH fact sheets',
  openfda_label: 'openFDA drug labels',
  pubmed: 'PubMed literature',
  livertox: 'LiverTox',
  supp_ai: 'SUPP.AI',
  ddid: 'DDID experimental records',
  nih_dsld: 'NIH DSLD product labels',
  fda_cyp_table: 'FDA CYP/transporter table',
  rxnav: 'RxNorm / RxNav',
}

export const CITATION_KIND_LABELS: Record<string, string> = {
  classification: 'Deterministic classification',
  statement: 'Source statement',
  mechanism: 'Mechanism graph',
  excerpt: 'Retrieved passage',
  fact: 'Catalogue fact',
  observation: 'Experimental record',
  hepatotoxicity: 'LiverTox',
  mention: 'SUPP.AI mention',
  product_label: 'NIH DSLD product label',
}

export const STATEMENT_TYPE_LABELS: Record<string, string> = {
  interaction: 'States an interaction or contraindication',
  precaution: 'Advises caution or monitoring',
  no_interaction_reported: 'States no interaction was found or reported',
  uncertain: 'Describes the evidence as uncertain',
  unclassified: 'Mention in an interaction context, without explicit wording',
}

export const USE_CATEGORY_LABELS: Record<string, string> = {
  well_established_use: 'Well-established use',
  traditional_use: 'Traditional use',
  not_applicable: 'Not applicable',
}

export const EVIDENCE_GROUP_ORDER = [
  'regulatory',
  'human',
  'laboratory',
  'other',
] as const

export type EvidenceGroupKey = (typeof EVIDENCE_GROUP_ORDER)[number]

export const EVIDENCE_GROUPS: Record<
  EvidenceGroupKey,
  { title: string; description: string }
> = {
  regulatory: {
    title: 'Regulatory & government information',
    description: 'Monographs, official labels and government summaries.',
  },
  human: {
    title: 'Human studies & reviews',
    description: 'Systematic reviews, trials, clinical studies, case reports and reviews.',
  },
  laboratory: {
    title: 'Laboratory & animal findings',
    description: 'These do not show an effect in people.',
  },
  other: {
    title: 'Other evidence',
    description: 'Traditional use, spontaneous reports and unclassified publications.',
  },
}
