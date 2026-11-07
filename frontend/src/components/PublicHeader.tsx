import type { ReactNode } from 'react'

import { LeafOrnament } from './BotanicalArt'
import { Eyebrow } from './ui'

/** Header band for the public information pages (About, Sources & methodology). */
export function PublicHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: string
  children: ReactNode
}) {
  return (
    <div className="relative overflow-hidden border-b border-line bg-sage-100">
      <div className="bg-dots-dark pointer-events-none absolute inset-0 opacity-60" />
      <LeafOrnament className="pointer-events-none absolute -right-8 -top-10 h-72 w-72 text-forest-600/15" />
      <div className="relative mx-auto max-w-6xl px-4 py-14 sm:px-6 lg:py-20">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-3 max-w-3xl font-display text-4xl font-semibold leading-[1.08] tracking-tight text-forest-950 sm:text-5xl">
          {title}
        </h1>
        <div className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-soft">{children}</div>
      </div>
    </div>
  )
}
