import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { Icon } from './icons'

const MARGIN = 8 // keep this far from the viewport edge
const MAX_WIDTH = 320
const GAP = 6

// Only one tooltip is open at a time: opening one closes the previous one (for example a hovered
// label and a keyboard-focused label).
let closeActive: (() => void) | null = null

/**
 * A short explanation for a label, shown on interaction instead of repeated in the page.
 *
 * - Pointer: opens on hover and stays open while the pointer moves from the label onto the bubble.
 * - Keyboard: opens on focus; Escape closes; Enter or Space toggles.
 * - Touch: opens on tap, closes on a tap elsewhere or on Escape.
 * - Accessibility: the explanation is always present as the button's accessible description, so
 *   nothing is available only through hover. The visible bubble is a visual duplicate.
 * - Position: fixed to the viewport, clamped to its edges and flipped above the label when there
 *   is no room below, so it never overflows or has to be scrolled.
 */
export function Tooltip({
  text,
  children,
  className = '',
  icon = true,
  triggerClassName,
}: {
  text: string
  children: ReactNode
  className?: string
  /** Show the small info mark that signals an explanation is available. */
  icon?: boolean
  /** Replaces the default (dotted-underline) look, for example to render the label as a badge. */
  triggerClassName?: string
}) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement | null>(null)
  const bubble = useRef<HTMLDivElement | null>(null)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastPointer = useRef<string>('')
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ left: number; top: number; width: number } | null>(null)

  function cancelClose() {
    if (closeTimer.current) clearTimeout(closeTimer.current)
    closeTimer.current = null
  }
  function openNow() {
    cancelClose()
    if (closeActive && closeActive !== hide) closeActive()
    closeActive = hide
    setOpen(true)
  }
  function hide() {
    cancelClose()
    setOpen(false)
  }
  function closeSoon() {
    cancelClose()
    closeTimer.current = setTimeout(() => setOpen(false), 160)
  }

  // Place the bubble inside the viewport.
  useLayoutEffect(() => {
    if (!open || !trigger.current) return
    const place = () => {
      if (!trigger.current) return
      const rect = trigger.current.getBoundingClientRect()
      const width = Math.min(MAX_WIDTH, window.innerWidth - 2 * MARGIN)
      const left = Math.min(
        Math.max(rect.left + rect.width / 2 - width / 2, MARGIN),
        window.innerWidth - width - MARGIN,
      )
      const height = bubble.current?.offsetHeight ?? 0
      const below = rect.bottom + GAP
      const fitsBelow = below + height <= window.innerHeight - MARGIN
      const top = fitsBelow ? below : Math.max(MARGIN, rect.top - GAP - height)
      setPosition({ left, top, width })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open])

  // Close on Escape and on a press anywhere outside the label and the bubble (touch dismissal).
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPress = (event: Event) => {
      const target = event.target as Node
      if (trigger.current?.contains(target) || bubble.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPress)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPress)
    }
  }, [open])

  useEffect(
    () => () => {
      cancelClose()
      if (closeActive === hide) closeActive = null
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  return (
    <span className={`inline-flex max-w-full ${className}`}>
      <button
        ref={trigger}
        type="button"
        aria-describedby={id}
        aria-expanded={open}
        onPointerDown={(event) => {
          lastPointer.current = event.pointerType
        }}
        onPointerEnter={(event) => {
          if (event.pointerType !== 'touch') openNow()
        }}
        onPointerLeave={(event) => {
          if (event.pointerType !== 'touch') closeSoon()
        }}
        onFocus={openNow}
        onBlur={closeSoon}
        onClick={() => {
          // Hover has already opened it for a mouse; touch and keyboard activation toggle.
          if (lastPointer.current === 'mouse') {
            openNow()
          } else {
            cancelClose()
            setOpen((value) => !value)
          }
          lastPointer.current = ''
        }}
        className={
          triggerClassName ??
          'inline-flex max-w-full items-center gap-1 rounded-md text-left cursor-help underline decoration-dotted decoration-muted/60 underline-offset-[3px] transition-colors hover:decoration-teal-600'
        }
      >
        <span className="min-w-0 break-words">{children}</span>
        {icon ? <Icon name="info" className="h-3 w-3 shrink-0 text-muted/70" /> : null}
      </button>
      <span id={id} className="sr-only">
        {text}
      </span>
      {open
        ? createPortal(
            <div
              ref={bubble}
              data-tooltip-bubble
              aria-hidden="true"
              onPointerEnter={(event) => {
                if (event.pointerType !== 'touch') cancelClose()
              }}
              onPointerLeave={(event) => {
                if (event.pointerType !== 'touch') closeSoon()
              }}
              style={{
                position: 'fixed',
                left: position?.left ?? MARGIN,
                top: position?.top ?? MARGIN,
                width: position?.width ?? Math.min(MAX_WIDTH, window.innerWidth - 2 * MARGIN),
                visibility: position ? 'visible' : 'hidden',
              }}
              className="animate-pop z-[60] rounded-lg bg-forest-950 px-3 py-2 text-xs leading-relaxed text-white shadow-lift ring-1 ring-white/10"
            >
              {text}
            </div>,
            document.body,
          )
        : null}
    </span>
  )
}
