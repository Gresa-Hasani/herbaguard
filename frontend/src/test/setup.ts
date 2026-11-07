import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom does not implement scrolling; layouts call it on navigation.
window.scrollTo = () => undefined

// jsdom has no PointerEvent; tooltips distinguish mouse, touch and pen by `pointerType`.
if (typeof window.PointerEvent === 'undefined') {
  class TestPointerEvent extends MouseEvent {
    pointerType: string
    constructor(type: string, init: MouseEventInit & { pointerType?: string } = {}) {
      super(type, init)
      this.pointerType = init.pointerType ?? ''
    }
  }
  window.PointerEvent = TestPointerEvent as unknown as typeof PointerEvent
}
