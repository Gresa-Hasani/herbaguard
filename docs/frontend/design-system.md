# Frontend design system and information architecture

Implemented on `feat/frontend-ui`. Source of truth for tokens: [`frontend/src/index.css`](../../frontend/src/index.css) (`@theme`).

## Information architecture

| Experience | Routes | Shell |
|---|---|---|
| Public product | `/` (landing), `/about`, `/sources` | `PublicLayout`: sticky top bar with an animated underline, footer with the medical disclaimer |
| Workspace | `/interactions`, `/explorer`, `/assistant` | `AppLayout`: dark forest rail with a sliding active indicator (desktop); compact top bar plus bottom navigation (mobile) |

The workspace rail links back to the public pages (Sources & methodology, About, home). The landing page has no registry counts or dataset totals; the source registry lives only on `/sources`.

## Palette

| Role | Token | Value |
|---|---|---|
| Brand (deep forest) | `forest-900` / `forest-700` | `#0b2f25` / `#17533f` |
| Botanical accent | `forest-500` | `#2d8567` |
| Quiet surfaces | `sage-50…300` | `#f3f6f1` … `#bccbba` |
| Page | `canvas` (ivory) | `#f7f6f1` |
| Surface levels | `surface`, `surface-2`, `surface-3` | `#ffffff`, `#f3f6f1`, `#e8eee6` |
| Text | `ink`, `ink-soft`, `muted` | `#12201b`, `#2f3f38`, `#55655e` |
| Borders | `line`, `line-strong` | `#dcdfd5`, `#c3cabb` |
| Interactive (muted teal) | `teal-500…700` | `#1f8a89` … `#126061` |
| Warnings and manufacturer information (terracotta) | `clay-50…800` | `#fbf0ea` … `#6f3217` |
| Evidence categories | `ev-regulatory`, `ev-clinical`, `ev-supplementary`, `ev-manufacturer` | teal, blue, violet, clay |
| Interaction classes | `class-a…e` | red, copper, violet, slate-blue, grey |

There is no yellow, mustard or amber. Class D and E are slate and grey, never green, so no class reads as "safe". Classes and evidence categories are always accompanied by a letter or label.

## Typography and icons

Display headings use a system serif stack (`Iowan Old Style`, `Palatino Linotype`, `Georgia`); body text uses Inter or the system sans. No web fonts are loaded. Icons are an inline SVG set in `components/icons.tsx` (24px grid, 1.75 stroke); there is no icon dependency and no emoji.

## Motion

CSS only. Page transition (`animate-page`), section entrance (`Reveal`), sliding navigation indicators, hover lifts, expanding disclosures, and the botanical branch draw-in. All of it is disabled under `prefers-reduced-motion`. `Reveal` leaves content visible unless the browser can report visibility, and a throttled scroll check backs up `IntersectionObserver`, so a section can never stay hidden.

## Manufacturer information

NIH DSLD content is always shown on a dashed, hatched terracotta surface with the exact notice: "Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified."
