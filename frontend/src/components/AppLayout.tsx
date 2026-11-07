import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { PUBLIC_NAV, WORKSPACE_NAV } from '../lib/constants'
import { BackendStatus } from './BackendStatus'
import { DisclaimerBanner } from './DisclaimerBanner'
import { ErrorBoundary } from './ErrorBoundary'
import { Icon } from './icons'
import { Logo } from './Logo'

const ITEM_PITCH_REM = 3 // item height (2.75rem) + gap (0.25rem)

const SHORT_LABELS: Record<string, string> = {
  '/interactions': 'Checker',
  '/explorer': 'Explorer',
  '/assistant': 'Assistant',
}

/**
 * The application shell: a dark forest rail with a sliding active indicator on desktop, a
 * compact top bar plus bottom navigation on mobile. Public pages use a different shell.
 */
export function AppLayout() {
  const { pathname } = useLocation()
  const [moreOpen, setMoreOpen] = useState(false)
  const activeIndex = WORKSPACE_NAV.findIndex(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  )

  useEffect(() => {
    setMoreOpen(false)
  }, [pathname])

  return (
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>

      {/* Desktop rail */}
      <div className="sticky top-0 hidden h-screen flex-col overflow-hidden bg-forest-900 text-forest-100 lg:flex">
        <div className="bg-dots pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative flex h-full flex-col px-4 py-6">
          <Link to="/" aria-label="HerbaGuard home" className="px-2">
            <Logo tone="light" />
          </Link>

          <p className="mt-9 px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-forest-300">
            Workspace
          </p>
          <nav aria-label="Workspace" className="relative mt-3">
            {activeIndex >= 0 ? (
              <span
                aria-hidden="true"
                className="absolute left-0 top-0 h-11 w-full rounded-lg bg-white/10 ring-1 ring-white/10 transition-transform duration-300 ease-out"
                style={{ transform: `translateY(${activeIndex * ITEM_PITCH_REM}rem)` }}
              >
                <span className="absolute left-0 top-2.5 h-6 w-1 rounded-r bg-forest-300" />
              </span>
            ) : null}
            <ul className="relative flex flex-col gap-1">
              {WORKSPACE_NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      `flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
                        isActive ? 'text-white' : 'text-forest-200 hover:text-white'
                      }`
                    }
                  >
                    <Icon name={item.icon} className="h-[18px] w-[18px]" />
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <p className="mt-9 px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-forest-300">
            Transparency
          </p>
          <ul className="mt-3 flex flex-col gap-1 text-sm">
            {PUBLIC_NAV.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className="flex h-10 items-center gap-3 rounded-lg px-3 text-forest-200 transition-colors hover:bg-white/5 hover:text-white"
                >
                  <Icon name={item.icon} className="h-[18px] w-[18px]" />
                  {item.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                to="/"
                className="flex h-10 items-center gap-3 rounded-lg px-3 text-forest-200 transition-colors hover:bg-white/5 hover:text-white"
              >
                <Icon name="home" className="h-[18px] w-[18px]" />
                HerbaGuard home
              </Link>
            </li>
          </ul>

          <div className="mt-auto space-y-3 border-t border-white/10 px-3 pt-4">
            <BackendStatus tone="dark" />
            <p className="text-[11px] leading-relaxed text-forest-300">
              An evidence-support tool for exploring sources. Not a diagnostic or treatment system.
            </p>
          </div>
        </div>
      </div>

      <div className="flex min-w-0 flex-col">
        {/* Mobile top bar */}
        <div className="sticky top-0 z-30 flex items-center justify-between border-b border-white/10 bg-forest-900 px-4 py-2.5 lg:hidden">
          <Link to="/" aria-label="HerbaGuard home">
            <Logo tone="light" />
          </Link>
          <div className="flex items-center gap-3">
            <BackendStatus tone="dark" />
            <button
              type="button"
              aria-label={moreOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((open) => !open)}
              className="rounded-md p-1.5 text-forest-100 hover:bg-white/10"
            >
              <Icon name={moreOpen ? 'x' : 'menu'} />
            </button>
          </div>
        </div>
        {moreOpen ? (
          <div className="animate-pop z-30 border-b border-line bg-surface px-4 py-3 shadow-lift lg:hidden">
            <ul className="space-y-1 text-sm">
              {[...PUBLIC_NAV, { to: '/', label: 'HerbaGuard home', icon: 'home' as const }].map(
                (item) => (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-ink hover:bg-surface-2"
                    >
                      <Icon name={item.icon} className="h-[18px] w-[18px] text-forest-600" />
                      {item.label}
                    </Link>
                  </li>
                ),
              )}
            </ul>
          </div>
        ) : null}

        <DisclaimerBanner />

        <main id="main" className="flex-1 px-4 pb-28 pt-8 sm:px-8 lg:px-10 lg:pb-14">
          <div className="mx-auto w-full max-w-6xl">
            <ErrorBoundary>
              <div key={pathname} className="animate-page">
                <Outlet />
              </div>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav
        aria-label="Workspace (mobile)"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        <div className="relative mx-auto max-w-md">
          {activeIndex >= 0 ? (
            <span
              aria-hidden="true"
              className="absolute left-0 top-0 h-0.5 w-1/3 bg-forest-600 transition-transform duration-300 ease-out"
              style={{ transform: `translateX(${activeIndex * 100}%)` }}
            />
          ) : null}
          <ul className="grid grid-cols-3">
            {WORKSPACE_NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    `flex flex-col items-center gap-1 px-2 py-2.5 text-[11px] font-semibold transition-colors ${
                      isActive ? 'text-forest-700' : 'text-muted'
                    }`
                  }
                >
                  <Icon name={item.icon} className="h-5 w-5" />
                  {SHORT_LABELS[item.to]}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>
    </div>
  )
}
