import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Tooltip } from '../components/Tooltip'

const TEXT = 'A short explanation of the label.'
const bubble = () => document.querySelector<HTMLElement>('[data-tooltip-bubble]')

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true })
}

afterEach(() => {
  vi.restoreAllMocks()
  setViewport(1024, 768)
})

describe('Tooltip', () => {
  it('always exposes the explanation as the accessible description, with no hover needed', () => {
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    expect(screen.getByRole('button', { name: 'Label', description: TEXT })).toBeInTheDocument()
    expect(bubble()).toBeNull() // nothing is drawn until the user interacts
  })

  it('opens on hover and keeps open while the pointer moves from the label onto the bubble', async () => {
    const user = userEvent.setup()
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    const trigger = screen.getByRole('button', { name: 'Label' })

    await user.hover(trigger)
    expect(bubble()).toHaveTextContent(TEXT)

    await user.unhover(trigger)
    await user.hover(bubble() as HTMLElement) // arrives before the close delay ends
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(bubble()).not.toBeNull()

    await user.unhover(bubble() as HTMLElement)
    await waitFor(() => expect(bubble()).toBeNull())
  })

  it('does not need a click on desktop and a click does not close a hovered tooltip', async () => {
    const user = userEvent.setup()
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    const trigger = screen.getByRole('button', { name: 'Label' })
    await user.hover(trigger)
    expect(bubble()).not.toBeNull()
    await user.click(trigger)
    expect(bubble()).not.toBeNull()
  })

  it('opens on keyboard focus and closes on Escape or when focus leaves', async () => {
    const user = userEvent.setup()
    render(
      <>
        <Tooltip text={TEXT}>First</Tooltip>
        <Tooltip text="Second explanation.">Second</Tooltip>
      </>,
    )
    await user.tab()
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    expect(bubble()).toHaveTextContent(TEXT)

    await user.keyboard('{Escape}')
    expect(bubble()).toBeNull()

    await user.keyboard('{Enter}') // keyboard activation toggles
    expect(bubble()).not.toBeNull()
    await user.keyboard('{Enter}')
    expect(bubble()).toBeNull()

    await user.tab() // moving on shows only the next explanation
    await waitFor(() => expect(bubble()).toHaveTextContent('Second explanation.'))
    expect(document.querySelectorAll('[data-tooltip-bubble]')).toHaveLength(1)
  })

  it('opens on tap, closes on a second tap, and ignores the synthetic hover of touch', () => {
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    const trigger = screen.getByRole('button', { name: 'Label' })

    fireEvent.pointerEnter(trigger, { pointerType: 'touch' })
    expect(bubble()).toBeNull() // touch hover does not open it on its own

    fireEvent.pointerDown(trigger, { pointerType: 'touch' })
    fireEvent.click(trigger)
    expect(bubble()).toHaveTextContent(TEXT)

    fireEvent.pointerDown(trigger, { pointerType: 'touch' })
    fireEvent.click(trigger)
    expect(bubble()).toBeNull()
  })

  it('closes when tapping elsewhere and when another tooltip is tapped', () => {
    render(
      <>
        <p>Answer text</p>
        <Tooltip text={TEXT}>One</Tooltip>
        <Tooltip text="Another explanation.">Two</Tooltip>
      </>,
    )
    const one = screen.getByRole('button', { name: 'One' })
    const two = screen.getByRole('button', { name: 'Two' })

    fireEvent.pointerDown(one, { pointerType: 'touch' })
    fireEvent.click(one)
    expect(bubble()).toHaveTextContent(TEXT)

    fireEvent.pointerDown(screen.getByText('Answer text'), { pointerType: 'touch' })
    expect(bubble()).toBeNull()

    fireEvent.pointerDown(one, { pointerType: 'touch' })
    fireEvent.click(one)
    fireEvent.pointerDown(two, { pointerType: 'touch' })
    fireEvent.click(two)
    expect(document.querySelectorAll('[data-tooltip-bubble]')).toHaveLength(1)
    expect(bubble()).toHaveTextContent('Another explanation.')
  })

  it('keeps the bubble inside a narrow viewport, even for a long explanation', async () => {
    setViewport(320, 600)
    const long = 'This is a long explanation. '.repeat(12).trim()
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      // a label at the far right edge of a phone screen
      return this.tagName === 'BUTTON'
        ? ({ left: 290, right: 330, width: 40, top: 100, bottom: 120, height: 20 } as DOMRect)
        : ({ left: 0, right: 0, width: 0, top: 0, bottom: 0, height: 0 } as DOMRect)
    })
    render(<Tooltip text={long}>Label</Tooltip>)
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Label' }), { pointerType: 'touch' })
    fireEvent.click(screen.getByRole('button', { name: 'Label' }))

    const el = bubble() as HTMLElement
    expect(el).toHaveTextContent(long)
    const left = parseFloat(el.style.left)
    const width = parseFloat(el.style.width)
    expect(width).toBeLessThanOrEqual(320 - 16) // never wider than the viewport minus margins
    expect(left).toBeGreaterThanOrEqual(8)
    expect(left + width).toBeLessThanOrEqual(320 - 8)
    expect(el.className).not.toContain('whitespace-nowrap') // long text wraps
  })

  it('places the bubble above the label when there is no room below', () => {
    setViewport(400, 600)
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(80)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.tagName === 'BUTTON'
        ? ({ left: 100, right: 160, width: 60, top: 560, bottom: 580, height: 20 } as DOMRect)
        : ({ left: 0, right: 0, width: 0, top: 0, bottom: 0, height: 0 } as DOMRect)
    })
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    fireEvent.focus(screen.getByRole('button', { name: 'Label' }))
    const top = parseFloat((bubble() as HTMLElement).style.top)
    expect(top).toBeLessThan(560) // above the label
    expect(top).toBeGreaterThanOrEqual(8)
  })

  it('repositions when the window is resized while open', () => {
    setViewport(800, 600)
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    fireEvent.focus(screen.getByRole('button', { name: 'Label' }))
    const before = parseFloat((bubble() as HTMLElement).style.width)
    act(() => {
      setViewport(300, 600)
      window.dispatchEvent(new Event('resize'))
    })
    expect(parseFloat((bubble() as HTMLElement).style.width)).toBeLessThan(before)
    expect(parseFloat((bubble() as HTMLElement).style.width)).toBeLessThanOrEqual(300 - 16)
  })

  it('draws a visual copy only: the bubble itself is hidden from assistive technology', () => {
    render(<Tooltip text={TEXT}>Label</Tooltip>)
    fireEvent.focus(screen.getByRole('button', { name: 'Label' }))
    expect(bubble()).toHaveAttribute('aria-hidden', 'true')
    // the description is still announced exactly once, from the always-present text
    expect(screen.getByRole('button', { name: 'Label', description: TEXT })).toBeInTheDocument()
  })

  it('keeps only one tooltip open when one label is hovered and another is focused', async () => {
    const user = userEvent.setup()
    render(
      <>
        <Tooltip text="First explanation.">First</Tooltip>
        <Tooltip text="Second explanation.">Second</Tooltip>
      </>,
    )
    await user.hover(screen.getByRole('button', { name: 'First' }))
    expect(bubble()).toHaveTextContent('First explanation.')
    act(() => screen.getByRole('button', { name: 'Second' }).focus())
    expect(document.querySelectorAll('[data-tooltip-bubble]')).toHaveLength(1)
    expect(bubble()).toHaveTextContent('Second explanation.')
  })
})
