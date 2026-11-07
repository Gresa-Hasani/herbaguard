import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { PUBLIC_NAV, WORKSPACE_NAV } from '../lib/constants'
import { BackendStatus } from './BackendStatus'
import { DisclaimerBanner } from './DisclaimerBanner'
import { ErrorBoundary } from './ErrorBoundary'
import { Icon } from './icons'
import { Logo } from './Logo'
import { ButtonLink } from './ui'

/** The public product shell: landing page, About and Sources & methodology. */
export function PublicLayout() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setOpen(false)
    if (pathname !== '/') window.scrollTo({ top: 0 })
  }, [pathname])

  const links = [
    ...(pathname === '/'
      ? [
          { to: '/#how', label: 'How it works' },
          { to: '/#evidence', label: 'Evidence-first' },
        ]
      : []),
    ...PUBLIC_NAV.map((item) => ({ to: item.to, label: item.label })),
  ]

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 border-b border-line/70 bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" aria-label="HerbaGuard home">
            <Logo />
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {links.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end
                className={({ isActive }) =>
                  `group relative rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive && !item.to.includes('#')
                      ? 'text-forest-800'
                      : 'text-ink-soft hover:text-forest-800'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {item.label}
                    <span
                      aria-hidden="true"
                      className={`absolute inset-x-3 -bottom-px h-0.5 origin-left rounded bg-forest-600 transition-transform duration-300 ${
                        isActive && !item.to.includes('#')
                          ? 'scale-x-100'
                          : 'scale-x-0 group-hover:scale-x-100'
                      }`}
                    />
                  </>
                )}
              </NavLink>
            ))}
            <ButtonLink to="/interactions" size="sm" iconEnd="arrow" className="ml-3">
              Open workspace
            </ButtonLink>
          </nav>

          <button
            type="button"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
            className="rounded-md p-2 text-forest-800 hover:bg-sage-100 md:hidden"
          >
            <Icon name={open ? 'x' : 'menu'} />
          </button>
        </div>

        {open ? (
          <div className="animate-pop border-t border-line bg-canvas px-4 pb-5 pt-3 md:hidden">
            <ul className="space-y-1">
              {links.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="block rounded-lg px-3 py-2.5 text-[15px] font-medium text-ink hover:bg-sage-100"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <ButtonLink to="/interactions" iconEnd="arrow" className="mt-3 w-full">
              Open workspace
            </ButtonLink>
          </div>
        ) : null}
      </header>

      <main id="main" className="flex-1">
        <ErrorBoundary>
          <div key={pathname} className="animate-page">
            <Outlet />
          </div>
        </ErrorBoundary>
      </main>

      <footer className="relative overflow-hidden bg-forest-950 text-forest-200">
        <div className="bg-dots pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
            <div>
              <Logo tone="light" />
              <p className="mt-4 max-w-sm text-sm leading-relaxed text-forest-300">
                Traceable herb–drug evidence for exploration and research. Built for EthnoHack 2026,
                Track 04: Digital Health &amp; Phytotherapy.
              </p>
              <div className="mt-5">
                <BackendStatus tone="dark" />
              </div>
            </div>
            <nav aria-label="Workspace links">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-forest-400">
                Workspace
              </p>
              <ul className="mt-4 space-y-2.5 text-sm">
                {WORKSPACE_NAV.map((item) => (
                  <li key={item.to}>
                    <Link to={item.to} className="transition-colors hover:text-white">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
            <nav aria-label="Transparency links">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-forest-400">
                Transparency
              </p>
              <ul className="mt-4 space-y-2.5 text-sm">
                {PUBLIC_NAV.map((item) => (
                  <li key={item.to}>
                    <Link to={item.to} className="transition-colors hover:text-white">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          <div className="mt-10">
            <DisclaimerBanner variant="panel" />
          </div>
          <p className="mt-6 text-xs text-forest-400">
            HerbaGuard is an evidence-support tool, not a diagnostic or treatment system.
          </p>
        </div>
      </footer>
    </div>
  )
}
