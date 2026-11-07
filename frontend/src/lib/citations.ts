import type { Citation, EvidenceTypeInfo } from './types'

/**
 * Plain-language description of a citation, built only from fields the API already returns.
 * Nothing here upgrades a category, infers clinical relevance from a source name, or fills in a
 * missing value: where a field is absent the helpers return nothing and the interface says so.
 */

export interface Described {
  label: string
  description: string
}

export interface Field {
  label: string
  value: string
}

/** What kind of record the citation points to (the citation's `kind`). */
const RECORD_TYPES: Record<Citation['kind'], Described> = {
  classification: {
    label: 'HerbaGuard classification',
    description:
      'The interaction class computed by HerbaGuard’s fixed rules from stored statements. This is a result, not a source document.',
  },
  statement: {
    label: 'Source statement',
    description: 'A sentence from a source document, with the herb or drug it is about.',
  },
  mechanism: {
    label: 'Mechanism relationship',
    description:
      'A herb–enzyme or herb–transporter relationship summarised from a source sentence; not a direct quotation.',
  },
  excerpt: {
    label: 'Retrieved passage',
    description:
      'A passage from a stored document that matched the question. Its search rank says nothing about its quality.',
  },
  fact: {
    label: 'Catalogue fact',
    description: 'A statement about what HerbaGuard has stored, not a study finding.',
  },
  observation: {
    label: 'Experimental record',
    description:
      'A database record describing findings from an experimental study. It does not automatically indicate a human clinical study.',
  },
  hepatotoxicity: {
    label: 'Liver-injury record',
    description: 'A LiverTox entry about liver injury linked to the herb.',
  },
  mention: {
    label: 'Literature mention',
    description:
      'A sentence from a paper that mentions the herb and the drug, found automatically. Not a confirmed interaction.',
  },
  product_label: {
    label: 'Manufacturer product label',
    description: 'Text printed by a manufacturer on a product label.',
  },
}

/** Tooltip for the source label of a HerbaGuard-generated item (no external document). */
export const GENERATED_SOURCE_TIP =
  'Computed by HerbaGuard’s fixed rules. There is no external source document behind this item.'

/** Citation kinds produced by HerbaGuard itself rather than taken from an external source. */
export function isGenerated(citation: Citation): boolean {
  return citation.kind === 'classification'
}

export function recordType(citation: Citation): Described {
  return RECORD_TYPES[citation.kind]
}

/**
 * The evidence category (the citation's `role`): why the item is in the answer. None of these
 * is a quality rating.
 */
const ROLES: Record<Citation['role'], Described> = {
  deterministic_classification: {
    label: 'Deterministic classification',
    description: 'Computed by fixed rules, not by the language model.',
  },
  direct_evidence: {
    label: 'Direct evidence',
    description:
      'Says something about this herb or drug in the source’s own words. It reports what the source states; it does not establish certainty.',
  },
  graph_context: {
    label: 'Mechanism context',
    description:
      'Background on how the herb may act on an enzyme or transporter. Supports a possible mechanism, not proof of an interaction in people.',
  },
  catalogue: {
    label: 'Catalogue fact',
    description: 'Describes what is stored, not what a study found.',
  },
  experimental_evidence: {
    label: 'Experimental evidence',
    description:
      'Evidence classified as experimental. This label alone does not establish clinical effectiveness or certainty.',
  },
  hepatotoxicity_evidence: {
    label: 'Liver-injury evidence',
    description:
      'The likelihood score is not an interaction class, and a missing entry is not evidence of liver safety.',
  },
  supplementary_mention: {
    label: 'Supplementary mention',
    description:
      'Context only, found automatically. It never decides an interaction class and is not a confirmed interaction.',
  },
  product_label_information: {
    label: 'Product-label information',
    description:
      'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.',
  },
}

export function evidenceCategory(citation: Citation): Described {
  return ROLES[citation.role]
}

/** The document or study type that came with the record (`evidence_type`). */
const DOCUMENT_TYPES: Record<string, string> = {
  REG: 'An official regulatory document, such as a monograph or a drug label.',
  GOV: 'A summary published by a government health agency.',
  SR: 'A published review that combines the results of other studies.',
  RCT: 'A randomised controlled trial.',
  CLIN: 'A clinical study that is not a randomised trial or a systematic review.',
  CASE: 'A report of one or a few cases.',
  ANIMAL: 'A study in animals. It does not show an effect in people.',
  INVITRO: 'A laboratory (cell or test-tube) study. It does not show an effect in people.',
  TRAD: 'Traditional-use information.',
  SPONT: 'A spontaneous report, for example of a suspected side effect.',
  COMP: 'A computational prediction.',
  REV: 'A review that is not a systematic review.',
  OTHER: 'A record that fits none of the other document types.',
}

export function documentType(info: EvidenceTypeInfo | null): Described | null {
  if (!info) return null
  return {
    label: info.label,
    description: `${DOCUMENT_TYPES[info.code] ?? 'Document or study type recorded for this item.'} It describes the kind of document, not its quality or certainty.`,
  }
}

/** Short explanation of a licence status exactly as recorded (shown in a tooltip). */
export function licenceStatusPlain(status: string): string {
  if (status === 'verified') return 'A verified licence is recorded for this source.'
  if (status === 'catalogue') return 'A catalogue-level licence is recorded. It has not been verified.'
  return 'The source’s redistribution permissions have not been verified. This does not imply permission to redistribute.'
}

/** Explanations of the extra restriction tags a source can carry. */
export const RESTRICTION_TIPS: Record<string, string> = {
  'Not redistributable':
    'The source’s content cannot be redistributed under the recorded conditions.',
  'Permission required': 'Additional permission from the owner is required to redistribute it.',
  'Local store only': 'This content is kept in a local store and is not redistributed.',
}

/** What the source label means: the registered name, what kind of source it is, who provides it. */
export function sourceTip(name: string, dataType: string | null, provider: string | null): string {
  return [
    `The source of this record: ${name}.`,
    dataType ? `${dataType}.` : null,
    provider ? `Provided by ${provider}.` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

// ------------------------------------------------------------------ study context and qualifiers

/**
 * Study details of an experimental record. The record's text is generated by HerbaGuard from the
 * dataset's own columns in a fixed order ("Species: …. design: …; n: …; timing: …; method: ….
 * Result: …"), so labelled fields can be read back. Only fields that are present are returned; a
 * value the dataset marks as not stated is shown as such, never replaced by a guess.
 */
const STUDY_FIELDS: [key: string, label: string][] = [
  ['design', 'Study design'],
  ['n', 'Sample size'],
  ['timing', 'Duration or timing'],
  ['method', 'Methods'],
  ['herb/food dose', 'Herb dose'],
  ['drug dose', 'Drug dose'],
  ['dosage form', 'Dosage form'],
  ['sample', 'Sample tested'],
]

export function studyContext(citation: Citation): Field[] {
  if (citation.kind !== 'observation') return []
  const text = citation.excerpt
  const fields: Field[] = []

  const species = /\bSpecies: (.+?)\. (?=[a-z]|Result:)/.exec(text)
  if (species) {
    const value = species[1].trim()
    fields.push({
      label: 'Species',
      value: /^not stated$/i.test(value) ? 'Not stated in the record' : value,
    })
  }

  const detailStart = species ? species.index + species[0].length : -1
  const detailEnd = text.indexOf('. Result:')
  if (detailStart >= 0 && detailEnd > detailStart) {
    const details = text.slice(detailStart, detailEnd)
    const keys = STUDY_FIELDS.map(([key]) => key.replace('/', '\\/')).join('|')
    const pattern = new RegExp(`(?:^|; )(${keys}): `, 'g')
    const marks = [...details.matchAll(pattern)]
    const found = new Map<string, string>()
    marks.forEach((mark, index) => {
      const start = (mark.index ?? 0) + mark[0].length
      const end = index + 1 < marks.length ? (marks[index + 1].index ?? details.length) : details.length
      found.set(mark[1], details.slice(start, end).trim())
    })
    for (const [key, label] of STUDY_FIELDS) {
      const value = found.get(key)
      if (value) fields.push({ label, value })
    }
  }
  return fields
}

const QUALIFIER_FIELDS: Record<string, string> = {
  'publication year': 'Publication year',
  'document date': 'Document date',
  'linked herbs': 'Linked herbs',
  'statement type': 'Statement type',
  about: 'About',
  conditions: 'Conditions',
  'study context': 'Study setting (as stated by the dataset)',
}

/** Splits the record's qualifier strings into labelled fields and free-text notes. */
export function qualifierDetails(qualifiers: string[]): { fields: Field[]; notes: string[] } {
  const fields: Field[] = []
  const notes: string[] = []
  for (const qualifier of qualifiers) {
    const split = qualifier.indexOf(': ')
    const key = split > 0 ? qualifier.slice(0, split).toLowerCase() : ''
    if (key in QUALIFIER_FIELDS) {
      fields.push({ label: QUALIFIER_FIELDS[key], value: qualifier.slice(split + 2).trim() })
    } else {
      notes.push(qualifier)
    }
  }
  return { fields, notes }
}
