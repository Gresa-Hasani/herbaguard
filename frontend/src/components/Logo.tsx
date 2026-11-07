export function LogoMark({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <rect width="48" height="48" rx="13" fill="#0b2f25" />
      <path d="M13 36c0-10 6-19 20-21 .6 12-4 21-16 21-1.4 0-2.9-.1-4-.2" fill="#dcede5" />
      <path
        d="M12 38c5-6 10-11 17-16"
        stroke="#0b2f25"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="35" cy="13" r="3.2" fill="#55a287" />
    </svg>
  )
}

export function Logo({ tone = 'dark' }: { tone?: 'dark' | 'light' }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark />
      <span
        className={`font-display text-xl font-semibold tracking-tight ${
          tone === 'light' ? 'text-white' : 'text-forest-900'
        }`}
      >
        HerbaGuard
      </span>
    </span>
  )
}
