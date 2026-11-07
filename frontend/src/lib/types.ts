/** Types mirroring backend schemas (herbaguard.api.schemas). */

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface MetaResponse {
  name: string
  version: string
  environment: string
  api_version: string
  disclaimer: string
}

export interface ReadinessCheck {
  name: string
  status: 'ok' | 'error'
  detail: string | null
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded'
  checks: ReadinessCheck[]
}

export interface NameOut {
  name: string
  name_type: 'accepted' | 'synonym' | 'common' | 'pharmaceutical'
  language: string | null
  source_code: string
}

export interface HerbRef {
  pharmaceutical_name: string
  common_name: string | null
  plant_part: string
}

export interface TaxonSummary {
  wfo_id: string
  scientific_name: string
  authorship: string | null
  family: string | null
  herbs: HerbRef[]
  matched_name: NameOut | null
}

export interface Identifiers {
  wfo_id: string
  ipni_id: string | null
  wcvp_plant_name_id: number | null
  gbif_key: number | null
  ncbi_tax_id: number | null
  powo_id: string | null
  wikidata_id: string | null
}

export interface Provenance {
  source_code: string
  source_name: string
  licence: string | null
  licence_status: string
  retrieved_url: string
  retrieved_at: string
  source_version: string | null
  extraction_method: string
  location: string | null
  excerpt: string | null
}

export interface EvidenceTypeInfo {
  code: string
  label: string
  basis: 'source_document' | 'nlm_publication_type'
  quality_assessed: false
  note: string
}

export interface EvidenceRef {
  id: string
  source_code: string
  external_id: string
  title: string
  url: string | null
  evidence_type: EvidenceTypeInfo
  document_date: string | null
  publication_year: number | null
}

export interface Indication {
  text: string
  use_category: string
  evidence: EvidenceRef
  provenance: Provenance[]
}

export interface Monograph {
  document: string
  title: string
  url: string | null
  document_date: string | null
  use_categories: string[]
  section_completeness: Record<string, string>
  interactions_section_states_none_reported: string[]
}

export interface TaxonDetail extends TaxonSummary {
  identifiers: Identifiers
  native_range: string | null
  names: NameOut[]
  indications: Indication[]
  monographs: Monograph[]
  provenance: Provenance[]
  counts: Record<string, number>
}

export interface DrugClass {
  code: string
  name: string
  level: number
  system: string
}

export interface Drug {
  rxcui: string
  name: string
  atc_classes: DrugClass[]
}

export interface EvidenceSummary extends EvidenceRef {
  herbs: string[]
  relations: string[]
  metadata: Record<string, unknown>
}

export interface EvidenceDetail extends EvidenceSummary {
  content: { section: string | null; text: string }[]
  provenance: Provenance[]
}

export interface Candidate {
  pharmaceutical_name: string
  common_name: string | null
  taxa: string[]
  matched_name: NameOut
}

export interface HerbResolution {
  query: string
  status: 'resolved' | 'ambiguous' | 'not_found'
  herb: HerbRef | null
  taxa: TaxonSummary[]
  matched_name: NameOut | null
  candidates: Candidate[]
  note: string | null
}

export interface DrugResolution {
  query: string
  status: 'resolved' | 'not_found' | 'lookup_failed'
  resolved_via: 'database' | 'rxnav' | null
  drug: Drug | null
  note: string | null
}

export interface Statement {
  id: string
  role: 'decisive' | 'context'
  statement_type: string
  statement_type_note: string
  source_code: string
  source_section: string | null
  use_category: string
  matched_via: 'drug' | 'class'
  drug: Drug | null
  drug_class: DrugClass | null
  object_label_verbatim: string
  subject_label_verbatim: string | null
  severity_wording: string | null
  conditions: string | null
  mechanism: string | null
  excerpt: string | null
  subject_check: 'not_applicable' | 'named_in_sentence' | 'interaction_section' | 'not_verified'
  subject_check_note: string | null
  evidence: EvidenceRef
  provenance: Provenance[]
  herbs: string[]
}

export interface MechanismPath {
  target_symbols: string
  herb_effect: {
    herb: string
    subject_kind: string
    subject_label: string
    target: { symbol: string; name: string; target_type: string }
    effect: string
    potency: string | null
    hedge_wording: string | null
    evidence_type: EvidenceTypeInfo
    source_code: string
    conditions: string | null
  }
  drug_role: {
    drug: { rxcui: string; name: string }
    target: { symbol: string; name: string; target_type: string }
    role: string
    role_label: string
    potency: string | null
    conditions: string | null
    source_code: string
  }
  qualifies_for_class_b: boolean
  reasons_not_qualifying: string[]
  conflicting: boolean
  experimental: boolean
  description: string
}

export interface MechanismAssessment {
  finding: string
  label: string
  explanation: string
  paths_total: number
  qualifying_paths: number
  herb_effects_stored: number
  drug_roles_stored: number
  rules: string
}

export interface Classification {
  interaction_class: 'A' | 'B' | 'C' | 'D' | 'E'
  class_label: string
  finding: string
  finding_label: string
  explanation: string
  reasons: string[]
  severity_wordings: string[]
  caveats: string[]
  method: string
}

export interface DrugCheckResult {
  drug: DrugResolution
  classification: Classification
  decisive_statements: Statement[]
  context_statements: Statement[]
  sources_searched: {
    source_code: string
    description: string
    retrieved_at: string | null
    used_for_classification: boolean
  }[]
  related_literature: Record<string, unknown>
  mechanism_paths: MechanismPath[]
  mechanism_assessment: MechanismAssessment | null
}

export interface InteractionCheckResponse {
  herb: HerbResolution
  results: DrugCheckResult[]
  disclaimer: string
}

export interface ProductLabelIngredient {
  ingredient: string
  amount_per_serving: string | null
  unit: string | null
  category: string | null
}

export interface ProductLabel {
  dsld_id: string
  product_name: string | null
  brand: string | null
  market_status: string | null
  upc: string | null
  label_url: string | null
  ingredients: ProductLabelIngredient[]
  precautions: string[]
  label_statement_count: number
  source_code: 'nih_dsld'
  licence_status: string
  redistributable: false
  provenance: Provenance[]
}

export interface SourceRow {
  code: string
  name: string
  provider: string
  homepage_url: string | null
  is_official: boolean
  licence: string | null
  licence_status: string
  redistributable: boolean
  last_run_status: string | null
  last_run_finished_at: string | null
  records: number
  // Recorded licence and retrieval metadata; null means "not recorded", never permission.
  licence_url?: string | null
  attribution?: string | null
  access_method?: string | null
  latest_retrieved_at?: string | null
  latest_source_version?: string | null
}

export interface CoverageRow {
  herb: HerbRef
  taxa: number
  monograph: string | null
  monograph_date: string | null
  fact_sheet: boolean
  label_coverage: string | null
  evidence_items: Record<string, number>
  active_statements: Record<string, number>
  pubmed_by_type: Record<string, number>
  type_note: string
}

export interface Citation {
  label: string
  kind:
    | 'classification'
    | 'statement'
    | 'mechanism'
    | 'excerpt'
    | 'fact'
    | 'observation'
    | 'hepatotoxicity'
    | 'mention'
    | 'product_label'
  role:
    | 'deterministic_classification'
    | 'direct_evidence'
    | 'graph_context'
    | 'catalogue'
    | 'experimental_evidence'
    | 'hepatotoxicity_evidence'
    | 'supplementary_mention'
    | 'product_label_information'
  evidence_item_id: string | null
  external_id: string | null
  source_code: string | null
  evidence_type: EvidenceTypeInfo | null
  title: string | null
  url: string | null
  location: string | null
  excerpt: string
  qualifiers: string[]
  provenance: Provenance[]
}

/** Present only when the answer was served from the validated answer cache. */
export interface CacheInfo {
  served_from_cache: boolean
  generated_at: string
  /** How long the model took when the answer was generated; no model ran for this request. */
  original_generation_ms: number
  validation_status: string
}

export interface AskResponse {
  status:
    | 'answered'
    | 'insufficient_evidence'
    | 'rejected_by_validation'
    | 'declined_dosing'
    | 'emergency_referral'
  question: string
  intent: string
  answer: string | null
  paragraphs: { text: string; citations: string[] }[]
  classification: {
    herb: string
    drug: string
    interaction_class: string
    class_label: string
    finding: string
    finding_label: string
    explanation: string
    severity_wordings: string[]
    caveats: string[]
    mechanism_assessment: MechanismAssessment | null
    method: string
    source: string
  }[]
  citations: Citation[]
  limitations: string[]
  insufficient_evidence: boolean
  entities: { kind: string; mention: string; name: string; identifier: string | null; note: string | null }[]
  personal_advice_requested: boolean
  validation: { rule: string; severity: 'removed' | 'critical' | 'warning'; message: string; paragraph: number | null }[]
  generation: {
    mode: 'model' | 'extractive' | 'none'
    provider: string
    model: string | null
    prompts: string[]
    input_tokens: number | null
    output_tokens: number | null
    duration_ms: number
    regenerations: number
    failed_attempts: { provider: string; kind: string }[]
  }
  retrieval: {
    mode_requested: string
    mode_used: string
    embedding_model: string | null
    candidates: Record<string, number>
    duration_ms: number
    notes: string[]
  } | null
  disclaimer: string
  cache?: CacheInfo | null
}

/** What is stored for one taxon, by kind of material. Groups are never merged. */
export interface TaxonCoverage {
  wfo_id: string
  scientific_name: string
  family: string | null
  taxonomic_status: string
  monograph_documents: number
  fact_sheet_items: number
  drug_label_mentions: number
  literature_clinical_items: number
  literature_interaction_items: number
  dsld_products: number
  supplementary_sources: Record<string, 'resolved' | 'candidate'>
  active_interaction_statements: number
}

export interface PlantCoverage {
  total: number
  items: TaxonCoverage[]
}
