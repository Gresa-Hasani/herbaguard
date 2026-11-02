import { useMeta } from '../hooks/useApi'
import { FALLBACK_DISCLAIMER } from '../lib/constants'

/** Persistent medical disclaimer, shown on every page. */
export function DisclaimerBanner() {
  const { data } = useMeta()
  return (
    <aside
      aria-label="Medical disclaimer"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-950"
    >
      <p className="mx-auto max-w-6xl">
        <strong className="font-semibold">Important:</strong>{' '}
        {data?.disclaimer ?? FALLBACK_DISCLAIMER}
      </p>
    </aside>
  )
}
