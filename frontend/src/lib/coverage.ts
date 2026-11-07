import type { TaxonCoverage } from './types'

/** Per-group totals for one taxon. The groups are reported separately and never summed together. */
export function coverageTotals(row: TaxonCoverage) {
  return {
    regulatory: row.monograph_documents + row.fact_sheet_items + row.drug_label_mentions,
    literature: row.literature_clinical_items + row.literature_interaction_items,
    labels: row.dsld_products,
  }
}
