import { useReadiness } from '../hooks/useApi'

type Tone = 'ok' | 'warn' | 'pending'

const DOT: Record<Tone, string> = {
  ok: 'bg-forest-400',
  warn: 'bg-class-b',
  pending: 'bg-class-e animate-pulse',
}

/** Small status indicator for the API and database (from the readiness probe). */
export function BackendStatus({ tone: surface = 'light' }: { tone?: 'light' | 'dark' }) {
  const { data, isPending, isError } = useReadiness()

  let tone: Tone = 'pending'
  let label = 'Checking service…'
  if (!isPending) {
    if (isError) {
      tone = 'warn'
      label = 'Service unavailable'
    } else if (data?.status === 'ok') {
      tone = 'ok'
      label = 'Service online'
    } else {
      tone = 'warn'
      label = 'Service degraded'
    }
  }

  return (
    <span
      role="status"
      className={`inline-flex items-center gap-2 text-xs ${
        surface === 'dark' ? 'text-forest-200' : 'text-muted'
      }`}
    >
      <span className="relative flex h-2 w-2">
        {tone === 'ok' ? (
          <span className="pulse-ring absolute inline-flex h-full w-full rounded-full bg-forest-400" />
        ) : null}
        <span aria-hidden="true" className={`relative h-2 w-2 rounded-full ${DOT[tone]}`} />
      </span>
      {label}
    </span>
  )
}
