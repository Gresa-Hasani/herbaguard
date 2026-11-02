import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="max-w-xl">
      <h1 className="text-2xl font-bold text-brand-900">Page not found</h1>
      <p className="mt-2 text-muted">The page you requested does not exist.</p>
      <Link to="/" className="mt-4 inline-block font-medium text-brand-700 underline">
        Back to the start page
      </Link>
    </section>
  )
}
