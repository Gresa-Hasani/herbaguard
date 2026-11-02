import { NavLink, Outlet } from 'react-router-dom'

import { NAV_ITEMS } from '../lib/constants'
import { BackendStatus } from './BackendStatus'
import { DisclaimerBanner } from './DisclaimerBanner'
import { ErrorBoundary } from './ErrorBoundary'

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>
      <DisclaimerBanner />
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2 text-lg font-bold text-brand-700">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            HerbaGuard
          </NavLink>
          <nav aria-label="Main">
            <ul className="flex flex-wrap gap-1 text-sm">
              {NAV_ITEMS.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      `rounded-md px-3 py-2 ${
                        isActive
                          ? 'bg-brand-50 font-semibold text-brand-700'
                          : 'text-muted hover:bg-canvas hover:text-ink'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-muted">
          <span>HerbaGuard — EthnoHack 2026, Track 04: Digital Health &amp; Phytotherapy</span>
          <BackendStatus />
        </div>
      </footer>
    </div>
  )
}
