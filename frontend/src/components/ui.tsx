import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

import { Icon, type IconName } from './icons'

type Tone = 'neutral' | 'brand' | 'warn' | 'danger' | 'info'

const BADGE_TONES: Record<Tone, string> = {
  neutral: 'border-line bg-surface-2 text-ink-soft',
  brand: 'border-forest-600/25 bg-forest-50 text-forest-700',
  warn: 'border-clay-600/30 bg-clay-50 text-clay-700',
  danger: 'border-danger/30 bg-danger-soft text-danger',
  info: 'border-teal-600/25 bg-teal-50 text-teal-700',
}

const ALERT_TONES: Record<Tone, { box: string; icon: IconName; iconColor: string }> = {
  neutral: { box: 'border-line bg-surface-2 text-ink', icon: 'info', iconColor: 'text-muted' },
  brand: { box: 'border-forest-600/25 bg-forest-50 text-forest-900', icon: 'check', iconColor: 'text-forest-600' },
  warn: { box: 'border-clay-600/30 bg-clay-50 text-clay-800', icon: 'alert', iconColor: 'text-clay-600' },
  danger: { box: 'border-danger/30 bg-danger-soft text-ink', icon: 'alert', iconColor: 'text-danger' },
  info: { box: 'border-teal-600/25 bg-teal-50 text-ink', icon: 'info', iconColor: 'text-teal-600' },
}

export function Panel({
  children,
  className = '',
  as: Tag = 'div',
}: {
  children: ReactNode
  className?: string
  as?: 'div' | 'section' | 'article' | 'aside'
}) {
  return (
    <Tag className={`rounded-xl border border-line bg-surface p-5 shadow-soft ${className}`}>
      {children}
    </Tag>
  )
}

export function Badge({
  children,
  tone = 'neutral',
  className = '',
}: {
  children: ReactNode
  tone?: Tone
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${BADGE_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

export function Alert({
  tone = 'info',
  title,
  children,
  role = 'status',
}: {
  tone?: Tone
  title?: string
  children: ReactNode
  role?: 'status' | 'alert' | 'note'
}) {
  const style = ALERT_TONES[tone]
  return (
    <div
      role={role === 'note' ? undefined : role}
      className={`flex gap-3 rounded-lg border p-4 text-sm ${style.box}`}
    >
      <Icon name={style.icon} className={`mt-0.5 h-4 w-4 ${style.iconColor}`} />
      <div className="min-w-0">
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className={title ? 'mt-1' : ''}>{children}</div>
      </div>
    </div>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-muted">
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-teal-600"
      />
      {label}
    </span>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`relative overflow-hidden rounded-md bg-sage-100 ${className}`}
    >
      <div className="shimmer absolute inset-0" />
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
  icon?: IconName
}) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 p-8 text-center">
      {icon ? (
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-sage-100 text-forest-600">
          <Icon name={icon} />
        </span>
      ) : null}
      <h3 className={`font-display text-lg font-semibold text-ink ${icon ? 'mt-3' : ''}`}>
        {title}
      </h3>
      <div className="mx-auto mt-2 max-w-xl text-sm text-muted">{children}</div>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={`text-xs font-semibold uppercase tracking-[0.14em] text-teal-700 ${className}`}
    >
      {children}
    </p>
  )
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        {description ? <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}

/** Workspace page header: icon tile, serif h1, one-line purpose. */
export function PageHeader({
  icon,
  eyebrow,
  title,
  children,
  aside,
}: {
  icon: IconName
  eyebrow: string
  title: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-6">
      <div className="flex max-w-3xl gap-4">
        <span className="mt-1 hidden h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-forest-800 text-forest-100 shadow-soft sm:flex">
          <Icon name={icon} className="h-6 w-6" />
        </span>
        <div>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            {title}
          </h1>
          <div className="mt-2 text-[15px] leading-relaxed text-muted">{children}</div>
        </div>
      </div>
      {aside}
    </header>
  )
}

export function Stat({ value, label, hint }: { value: ReactNode; label: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="font-display text-2xl font-semibold tracking-tight text-forest-900">{value}</p>
      <p className="mt-1 text-sm font-medium text-ink">{label}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  )
}

export function ExternalLink({
  href,
  children,
  className = '',
}: {
  href: string | null
  children: ReactNode
  className?: string
}) {
  if (!href) return <span className={className}>{children}</span>
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={`underline decoration-line-strong underline-offset-2 transition-colors hover:text-teal-700 hover:decoration-teal-500 ${className}`}
    >
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  )
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  )
}

/** Expandable region with an animated chevron; native <details> keeps it accessible. */
export function Disclosure({
  title,
  children,
  className = '',
  open,
}: {
  title: ReactNode
  children: ReactNode
  className?: string
  open?: boolean
}) {
  return (
    <details
      open={open}
      className={`group rounded-lg border border-line bg-surface transition-colors open:bg-surface open:shadow-soft ${className}`}
    >
      <summary className="flex items-center justify-between gap-3 rounded-lg px-4 py-3 text-sm font-medium text-ink-soft hover:bg-surface-2 hover:text-ink">
        <span>{title}</span>
        <Icon
          name="chevron"
          className="h-4 w-4 text-muted transition-transform duration-200 group-open:rotate-180"
        />
      </summary>
      <div className="animate-pop border-t border-line px-4 py-4">{children}</div>
    </details>
  )
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-forest-700 text-white shadow-soft hover:bg-forest-800 active:bg-forest-900 disabled:bg-sage-200 disabled:text-muted disabled:shadow-none',
  secondary:
    'border border-line-strong bg-surface text-ink hover:border-forest-500 hover:bg-forest-50 disabled:text-muted disabled:hover:bg-surface',
  ghost: 'text-forest-700 hover:bg-forest-50',
  danger:
    'border border-danger/40 bg-surface text-danger hover:bg-danger-soft disabled:text-muted',
}

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'gap-1.5 px-3 py-1.5 text-sm',
  md: 'gap-2 px-4 py-2.5 text-sm',
  lg: 'gap-2 px-6 py-3.5 text-base',
}

function buttonClasses(variant: ButtonVariant, size: ButtonSize, extra = '') {
  return `inline-flex items-center justify-center rounded-lg font-semibold transition-all duration-150 disabled:cursor-not-allowed ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${extra}`
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconEnd,
  className = '',
  children,
  ...props
}: {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: IconName
  iconEnd?: IconName
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" {...props} className={buttonClasses(variant, size, className)}>
      {icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
      {iconEnd ? <Icon name={iconEnd} className="h-4 w-4" /> : null}
    </button>
  )
}

export function ButtonLink({
  variant = 'primary',
  size = 'md',
  iconEnd,
  className = '',
  children,
  ...props
}: {
  variant?: ButtonVariant
  size?: ButtonSize
  iconEnd?: IconName
} & LinkProps) {
  return (
    <Link {...props} className={buttonClasses(variant, size, `group ${className}`)}>
      {children}
      {iconEnd ? (
        <Icon
          name={iconEnd}
          className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
        />
      ) : null}
    </Link>
  )
}
