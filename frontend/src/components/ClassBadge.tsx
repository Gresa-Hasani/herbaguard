import { classMeta } from '../lib/format'

const TILE: Record<string, string> = {
  A: 'bg-class-a',
  B: 'bg-class-b',
  C: 'bg-class-c',
  D: 'bg-class-d',
  E: 'bg-class-e',
}

const TEXT: Record<string, string> = {
  A: 'text-class-a',
  B: 'text-class-b',
  C: 'text-class-c',
  D: 'text-class-d',
  E: 'text-class-e',
}

/**
 * The interaction class as the backend returned it: a solid letter tile plus its label. The
 * letter is never recoloured to suggest safety; D and E are neutral slate/grey, not green.
 */
export function ClassBadge({
  letter,
  label,
  size = 'md',
}: {
  letter: string
  label?: string
  size?: 'sm' | 'md' | 'lg'
}) {
  const meta = classMeta(letter)
  const key = meta.letter
  const tile =
    size === 'lg'
      ? 'h-16 w-16 rounded-xl text-4xl'
      : size === 'sm'
        ? 'h-6 w-6 rounded-md text-sm'
        : 'h-9 w-9 rounded-lg text-xl'
  const text = size === 'lg' ? 'text-base' : 'text-sm'
  return (
    <span className="inline-flex items-center gap-2.5">
      <span
        aria-hidden="true"
        className={`inline-flex shrink-0 items-center justify-center font-display font-semibold leading-none text-white shadow-soft ${TILE[key]} ${tile}`}
      >
        {letter}
      </span>
      <span className={`${text} font-semibold ${TEXT[key]}`}>{label ?? meta.label}</span>
    </span>
  )
}
