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
  phase: number
}

export const NAV_ITEMS: NavItem[] = [
  {
    to: '/explorer',
    label: 'Herbal Explorer',
    description: 'Medicinal plants with taxonomy, regulatory status and sources.',
    phase: 6,
  },
  {
    to: '/interactions',
    label: 'Interaction Check',
    description: 'Herb–drug combinations with graded, traceable evidence.',
    phase: 6,
  },
  {
    to: '/evidence',
    label: 'Evidence',
    description: 'Studies, trials and monographs behind each finding.',
    phase: 6,
  },
  {
    to: '/assistant',
    label: 'Evidence Assistant',
    description: 'Questions answered only from cited, retrieved sources.',
    phase: 6,
  },
  {
    to: '/safety',
    label: 'Safety Dashboard',
    description: 'Safety concerns, reported events and data coverage.',
    phase: 6,
  },
]
