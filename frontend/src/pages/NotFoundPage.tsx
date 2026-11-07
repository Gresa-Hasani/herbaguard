import { LeafOrnament } from '../components/BotanicalArt'
import { ButtonLink } from '../components/ui'

export function NotFoundPage() {
  return (
    <section className="relative mx-auto max-w-2xl overflow-hidden px-4 py-24 text-center sm:px-6">
      <LeafOrnament className="mx-auto h-24 w-24 text-forest-600/40" />
      <h1 className="mt-6 font-display text-4xl font-semibold text-forest-950">Page not found</h1>
      <p className="mt-3 text-ink-soft">The page you requested does not exist.</p>
      <div className="mt-8 flex justify-center gap-3">
        <ButtonLink to="/" iconEnd="arrow">
          Back to the start page
        </ButtonLink>
        <ButtonLink to="/interactions" variant="secondary">
          Open workspace
        </ButtonLink>
      </div>
    </section>
  )
}
