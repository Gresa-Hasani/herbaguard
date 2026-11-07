import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Reveal } from '../components/Reveal'

class SilentObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return []
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Reveal entrance effect', () => {
  it('leaves content visible when the browser cannot report visibility', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    render(
      <Reveal>
        <p>Evidence tier</p>
      </Reveal>,
    )
    const element = screen.getByText('Evidence tier').parentElement as HTMLElement
    expect(element.dataset.reveal).toBeUndefined()
    expect(screen.getByText('Evidence tier')).toBeVisible()
  })

  it('shows content that starts on screen immediately', () => {
    vi.stubGlobal('IntersectionObserver', SilentObserver)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      top: 40,
    } as DOMRect)
    render(
      <Reveal>
        <p>Hero</p>
      </Reveal>,
    )
    expect((screen.getByText('Hero').parentElement as HTMLElement).dataset.reveal).toBe('shown')
  })

  it('reveals off-screen content on scroll even if the observer never fires', async () => {
    vi.stubGlobal('IntersectionObserver', SilentObserver)
    let top = 5000
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
      () => ({ top }) as DOMRect,
    )
    render(
      <Reveal>
        <p>Below the fold</p>
      </Reveal>,
    )
    const element = screen.getByText('Below the fold').parentElement as HTMLElement
    expect(element.dataset.reveal).toBe('pending')

    // Still off screen: a scroll must not reveal it.
    window.dispatchEvent(new Event('scroll'))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(element.dataset.reveal).toBe('pending')

    top = 120
    window.dispatchEvent(new Event('scroll'))
    await waitFor(() => expect(element.dataset.reveal).toBe('shown'))
  })
})
