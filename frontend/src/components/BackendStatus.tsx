import { useReadiness } from '../hooks/useApi'

type Tone = 'ok' | 'warn' | 'pending'

const DOT: Record<Tone, string> = {
  ok: 'bg-brand-600',
  warn: 'bg-class-a',
  pending: 'bg-class-e animate-pulse',
}

/** Small status indicator for the API and database (from the readiness probe). */
export function BackendStatus() {
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
    <span role="status" className="inline-flex items-center gap-2 text-xs text-muted">
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[tone]}`} />
      {label}
    </span>
  )
}
