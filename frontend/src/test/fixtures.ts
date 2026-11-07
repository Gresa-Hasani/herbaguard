import type {
  AskResponse,
  Citation,
  CoverageRow,
  EvidenceSummary,
  InteractionCheckResponse,
  MetaResponse,
  Page,
  ProductLabel,
  Provenance,
  SourceRow,
  TaxonDetail,
  TaxonSummary,
} from '../lib/types'

export const WFO = 'wfo-0000728093'
export const LABEL_ID = '1001'

export const META: MetaResponse = {
  name: 'HerbaGuard',
  version: '0.1.0',
  environment: 'test',
  api_version: 'v1',
  disclaimer: 'Disclaimer text served by the API.',
}

export const PROVENANCE: Provenance = {
  source_code: 'ema_hmpc',
  source_name: 'EMA HMPC monographs',
  licence: 'EMA terms of use',
  licence_status: 'verified',
  retrieved_url: 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba',
  retrieved_at: '2026-01-15T10:00:00Z',
  source_version: '2024',
  extraction_method: 'structured_parse',
  location: 'Section 4.5',
  excerpt: 'St John’s wort may reduce the anticoagulant effect of warfarin.',
}

export const LABEL_PROVENANCE: Provenance = {
  source_code: 'nih_dsld',
  source_name: 'NIH DSLD product labels',
  licence: null,
  licence_status: 'unverified',
  retrieved_url: 'https://dsld.od.nih.gov/label/1001',
  retrieved_at: '2026-02-01T09:30:00Z',
  source_version: null,
  extraction_method: 'label_parse',
  location: 'Precautions',
  excerpt: null,
}

export const TAXON: TaxonSummary = {
  wfo_id: WFO,
  scientific_name: 'Hypericum perforatum',
  authorship: 'L.',
  family: 'Hypericaceae',
  herbs: [
    {
      pharmaceutical_name: 'Hyperici herba',
      common_name: "St John's wort",
      plant_part: 'flowering top',
    },
  ],
  matched_name: null,
}

export const TAXON_PAGE: Page<TaxonSummary> = {
  items: [TAXON],
  total: 1,
  limit: 12,
  offset: 0,
}

export const EVIDENCE_ITEM: EvidenceSummary = {
  id: 'ev-1',
  source_code: 'ema_hmpc',
  external_id: 'EMA/HMPC/123456/2015',
  title: 'European Union herbal monograph on Hypericum perforatum L., herba',
  url: 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba',
  evidence_type: {
    code: 'REG',
    label: 'Regulatory monograph',
    basis: 'source_document',
    quality_assessed: false,
    note: 'Official regulatory assessment.',
  },
  document_date: '2024-02-01',
  publication_year: null,
  herbs: ["St John's wort"],
  relations: ['monograph'],
  metadata: {},
}

export const EVIDENCE_PAGE: Page<EvidenceSummary> = {
  items: [EVIDENCE_ITEM],
  total: 1,
  limit: 50,
  offset: 0,
}

export const DETAIL: TaxonDetail = {
  ...TAXON,
  identifiers: {
    wfo_id: WFO,
    ipni_id: '223456-1',
    wcvp_plant_name_id: 12345,
    gbif_key: null,
    ncbi_tax_id: 65561,
    powo_id: null,
    wikidata_id: 'Q158130',
  },
  native_range: 'Europe, western Asia and North Africa',
  names: [
    {
      name: 'Hypericum perforatum',
      name_type: 'accepted',
      language: 'la',
      source_code: 'wfo',
    },
    {
      name: "St John's wort",
      name_type: 'common',
      language: 'en',
      source_code: 'wfo',
    },
  ],
  indications: [
    {
      text: 'Traditional herbal medicinal product for mild depressive episodes.',
      use_category: 'traditional_use',
      evidence: EVIDENCE_ITEM,
      provenance: [PROVENANCE],
    },
  ],
  monographs: [
    {
      document: 'EMA/HMPC/123456/2015',
      title: 'European Union herbal monograph on Hypericum perforatum L., herba',
      url: 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba',
      document_date: '2024-02-01',
      use_categories: ['traditional_use'],
      section_completeness: { indications: 'present', interactions: 'present' },
      interactions_section_states_none_reported: [],
    },
  ],
  provenance: [PROVENANCE],
  counts: { evidence_items: 1, monographs: 1 },
}

export const LABEL: ProductLabel = {
  dsld_id: LABEL_ID,
  product_name: 'SJW 300',
  brand: 'Example Botanicals',
  market_status: 'On Market',
  upc: '0 00000 00001 1',
  label_url: 'https://dsld.od.nih.gov/label/1001',
  ingredients: [
    {
      ingredient: "St John's wort (Hypericum perforatum)",
      amount_per_serving: '300',
      unit: 'mg',
      category: 'Botanical',
    },
  ],
  precautions: ['Consult your physician if you take anticoagulants.'],
  label_statement_count: 12,
  source_code: 'nih_dsld',
  licence_status: 'unverified',
  redistributable: false,
  provenance: [LABEL_PROVENANCE],
}

export const LABEL_PAGE: Page<ProductLabel> = {
  items: [LABEL],
  total: 1,
  limit: 20,
  offset: 0,
}

export const EMPTY_LABEL_PAGE: Page<ProductLabel> = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
}

export const SOURCES: SourceRow[] = [
  {
    code: 'ema_hmpc',
    name: 'EMA HMPC monographs',
    provider: 'European Medicines Agency',
    homepage_url: 'https://www.ema.europa.eu/',
    is_official: true,
    licence: 'EMA terms of use',
    licence_status: 'verified',
    redistributable: true,
    last_run_status: 'succeeded',
    last_run_finished_at: '2026-02-01T10:00:00Z',
    records: 120,
  },
  {
    code: 'nih_dsld',
    name: 'NIH DSLD product labels',
    provider: 'National Institutes of Health',
    homepage_url: 'https://dsld.od.nih.gov/',
    is_official: true,
    licence: null,
    licence_status: 'unverified',
    redistributable: false,
    last_run_status: 'succeeded',
    last_run_finished_at: '2026-02-02T10:00:00Z',
    records: 15506,
  },
]

export const COVERAGE: CoverageRow[] = [
  {
    herb: TAXON.herbs[0],
    taxa: 1,
    monograph: 'EMA/HMPC/123456/2015',
    monograph_date: '2024-02-01',
    fact_sheet: false,
    label_coverage: 'present',
    evidence_items: { REG: 1 },
    active_statements: { ema_hmpc: 1 },
    pubmed_by_type: {},
    type_note: 'Document type is not a quality rating.',
  },
]

const STATEMENT = {
  id: 'stmt-1',
  role: 'decisive' as const,
  statement_type: 'interaction',
  statement_type_note: 'The source states an interaction.',
  source_code: 'ema_hmpc',
  source_section: '4.5 Interactions',
  use_category: 'well_established_use',
  matched_via: 'drug' as const,
  drug: { rxcui: '202421', name: 'warfarin', atc_classes: [] },
  drug_class: null,
  object_label_verbatim: 'warfarin',
  subject_label_verbatim: "St John's wort",
  severity_wording: 'not recommended',
  conditions: null,
  mechanism: 'Enzyme induction',
  excerpt:
    'St John’s wort may reduce the anticoagulant effect of warfarin. Concomitant use is not recommended.',
  subject_check: 'named_in_sentence' as const,
  subject_check_note: 'Warfarin is named in the sentence.',
  evidence: EVIDENCE_ITEM,
  provenance: [PROVENANCE],
  herbs: ["St John's wort"],
}

export const INTERACTION_RESPONSE: InteractionCheckResponse = {
  herb: {
    query: 'Hyperici herba',
    status: 'resolved',
    herb: TAXON.herbs[0],
    taxa: [TAXON],
    matched_name: null,
    candidates: [],
    note: null,
  },
  results: [
    {
      drug: {
        query: 'warfarin',
        status: 'resolved',
        resolved_via: 'database',
        drug: { rxcui: '202421', name: 'warfarin', atc_classes: [] },
        note: null,
      },
      classification: {
        interaction_class: 'A',
        class_label: 'Documented',
        finding: 'interaction',
        finding_label: 'Documented interaction reported in an authoritative source',
        explanation:
          'An EMA monograph states that concomitant use of St John’s wort and warfarin is not recommended.',
        reasons: ['An authoritative source states the interaction explicitly.'],
        severity_wordings: ['not recommended'],
        caveats: ['The source does not quantify the risk for an individual patient.'],
        method: 'Fixed rule set applied to stored statements.',
      },
      decisive_statements: [STATEMENT],
      context_statements: [],
      sources_searched: [
        {
          source_code: 'ema_hmpc',
          description: 'EMA HMPC monographs',
          retrieved_at: '2026-02-01T10:00:00Z',
          used_for_classification: true,
        },
      ],
      related_literature: {},
      mechanism_paths: [],
      mechanism_assessment: null,
    },
  ],
  disclaimer: 'Not medical advice. Absence of an interaction is not evidence of safety.',
}

export const INTERACTION_NO_EVIDENCE: InteractionCheckResponse = {
  ...INTERACTION_RESPONSE,
  results: [
    {
      ...INTERACTION_RESPONSE.results[0],
      classification: {
        ...INTERACTION_RESPONSE.results[0].classification,
        interaction_class: 'D',
        class_label: 'No interaction evidence found',
        finding: 'no_evidence',
        finding_label: 'No interaction evidence found in the sources searched',
        explanation: 'The sources searched contained no interaction statement for this pair.',
        reasons: ['No decisive statement was found.'],
        severity_wordings: [],
        caveats: ['This is not evidence that the combination is safe.'],
      },
      decisive_statements: [],
    },
  ],
}

const CLASSIFICATION_CITATION: Citation = {
  label: 'C1',
  kind: 'classification',
  role: 'deterministic_classification',
  evidence_item_id: null,
  external_id: null,
  source_code: null,
  evidence_type: null,
  title: 'St John’s wort + warfarin — class A',
  url: null,
  location: null,
  excerpt: 'Deterministic classification: Documented. Finding: Documented interaction.',
  qualifiers: ['Backend A–E classification, not generated text.'],
  provenance: [],
}

const STATEMENT_CITATION: Citation = {
  label: 'S1',
  kind: 'statement',
  role: 'direct_evidence',
  evidence_item_id: 'ev-1',
  external_id: 'EMA/HMPC/123456/2015',
  source_code: 'ema_hmpc',
  evidence_type: EVIDENCE_ITEM.evidence_type,
  title: 'European Union herbal monograph on Hypericum perforatum L., herba',
  url: 'https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba',
  location: 'Section 4.5 Interactions',
  excerpt: 'Concomitant use of St John’s wort and warfarin is not recommended.',
  qualifiers: ['Important: the source words the interaction as “not recommended”.'],
  provenance: [PROVENANCE],
}

const PRODUCT_LABEL_CITATION: Citation = {
  label: 'P1',
  kind: 'product_label',
  role: 'product_label_information',
  evidence_item_id: null,
  external_id: '1001',
  source_code: 'nih_dsld',
  evidence_type: null,
  title: 'SJW 300',
  url: 'https://dsld.od.nih.gov/label/1001',
  location: 'Precautions',
  excerpt: 'Consult your physician if you take anticoagulants.',
  qualifiers: ['Manufacturer wording; not clinical evidence.'],
  provenance: [LABEL_PROVENANCE],
}

const GENERATION: AskResponse['generation'] = {
  mode: 'model',
  provider: 'test-provider',
  model: 'test-model',
  prompts: ['answer'],
  input_tokens: 900,
  output_tokens: 120,
  duration_ms: 1450,
  regenerations: 0,
  failed_attempts: [],
}

const RETRIEVAL: AskResponse['retrieval'] = {
  mode_requested: 'hybrid',
  mode_used: 'hybrid',
  embedding_model: 'test-embed',
  candidates: { statements: 8, evidence: 3 },
  duration_ms: 220,
  notes: [],
}

export const ASK_RESPONSE: AskResponse = {
  status: 'answered',
  question: 'What does the evidence say about St John’s wort and warfarin?',
  intent: 'interaction',
  answer:
    'EMA guidance states that St John’s wort may reduce the effect of warfarin, and concomitant use is not recommended [S1]. This is a documented interaction, not a prediction for an individual [C1].',
  paragraphs: [
    {
      text: 'EMA guidance states that St John’s wort may reduce the effect of warfarin, and concomitant use is not recommended.',
      citations: ['S1', 'C1'],
    },
  ],
  classification: [
    {
      herb: "St John's wort",
      drug: 'warfarin',
      interaction_class: 'A',
      class_label: 'Documented',
      finding: 'interaction',
      finding_label: 'Documented interaction reported in an authoritative source',
      explanation: 'An EMA monograph states the interaction explicitly.',
      severity_wordings: ['not recommended'],
      caveats: ['The source does not quantify individual risk.'],
      mechanism_assessment: null,
      method: 'Fixed rule set.',
      source: 'deterministic',
    },
  ],
  citations: [STATEMENT_CITATION, CLASSIFICATION_CITATION],
  limitations: [
    'The answer is limited to the retrieved sources and is not medical advice.',
    'The source does not quantify the risk for an individual patient.',
  ],
  insufficient_evidence: false,
  entities: [
    {
      kind: 'herb',
      mention: "St John's wort",
      name: 'Hyperici herba',
      identifier: WFO,
      note: null,
    },
    { kind: 'drug', mention: 'warfarin', name: 'warfarin', identifier: '202421', note: null },
  ],
  personal_advice_requested: false,
  validation: [],
  generation: GENERATION,
  retrieval: RETRIEVAL,
  disclaimer: 'Not medical advice. Absence of an interaction is not evidence of safety.',
}

export const ASK_WITH_LABEL: AskResponse = {
  ...ASK_RESPONSE,
  citations: [STATEMENT_CITATION, PRODUCT_LABEL_CITATION],
}

export const ASK_INSUFFICIENT: AskResponse = {
  ...ASK_RESPONSE,
  status: 'insufficient_evidence',
  answer: null,
  paragraphs: [],
  classification: [],
  citations: [],
  limitations: ['No retrieved evidence supported an answer.'],
  insufficient_evidence: true,
}
