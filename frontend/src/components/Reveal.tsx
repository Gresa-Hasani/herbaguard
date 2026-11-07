import { useLayoutEffect, useRef, type CSSProperties, type ElementType, type ReactNode } from 'react'

/**
 * Section entrance effect. Content is visible by default; it is only hidden (and then revealed
 * on scroll) once the browser can report visibility, so nothing is lost without JavaScript, in
 * tests or for users who prefer reduced motion (the stylesheet shows it immediately).
 *
 * IntersectionObserver is the primary trigger. A throttled scroll check backs it up, because
 * observers can be delayed or suspended in background or embedded views; a section must never
 * stay hidden once it is on screen.
 */
export function Reveal({
  as: Tag = 'div',
  delay = 0,
  className = '',
  children,
}: {
  as?: ElementType
  delay?: number
  className?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLElement | null>(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element || typeof IntersectionObserver === 'undefined') return

    const onScreen = () => element.getBoundingClientRect().top < window.innerHeight * 0.92
    if (onScreen()) {
      element.dataset.reveal = 'shown'
      return
    }

    element.dataset.reveal = 'pending'
    let frame = 0
    const show = () => {
      element.dataset.reveal = 'shown'
      cleanup()
    }
    const check = () => {
      frame = 0
      if (onScreen()) show()
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(check)
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) show()
      },
      { threshold: 0.05, rootMargin: '0px 0px -6% 0px' },
    )
    function cleanup() {
      observer.disconnect()
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
    observer.observe(element)
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    return cleanup
  }, [])

  const style = { '--reveal-delay': `${delay}ms` } as CSSProperties
  return (
    <Tag ref={ref} className={className} style={style}>
      {children}
    </Tag>
  )
}
