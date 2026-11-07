import { useMeta } from '../hooks/useApi'
import { FALLBACK_DISCLAIMER } from '../lib/constants'
import { Icon } from './icons'

/**
 * Persistent medical disclaimer on every page. `strip` is the slim workspace version; `panel` is
 * the larger version for the public footer. The text always comes from the backend when loaded.
 */
export function DisclaimerBanner({ variant = 'strip' }: { variant?: 'strip' | 'panel' }) {
  const { data } = useMeta()
  const text = data?.disclaimer ?? FALLBACK_DISCLAIMER

  if (variant === 'panel') {
    return (
      <aside
        aria-label="Medical disclaimer"
        className="flex gap-3 rounded-xl border border-forest-700 bg-forest-800/60 p-4 text-sm leading-relaxed text-forest-100"
      >
        <Icon name="shield" className="mt-0.5 h-5 w-5 text-forest-300" />
        <p>
          <strong className="font-semibold text-white">Important:</strong> {text}
        </p>
      </aside>
    )
  }
  return (
    <aside
      aria-label="Medical disclaimer"
      className="border-b border-line bg-surface-2 px-4 py-2 text-xs leading-relaxed text-ink-soft sm:px-8"
    >
      <p className="mx-auto flex max-w-6xl items-start gap-2">
        <Icon name="info" className="mt-0.5 h-3.5 w-3.5 text-teal-600" />
        <span>
          <strong className="font-semibold text-ink">Important:</strong> {text}
        </span>
      </p>
    </aside>
  )
}
