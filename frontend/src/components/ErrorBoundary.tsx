import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/** Catches rendering errors so one broken view never blanks the whole application. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Only the error name and component stack are logged — never user input.
    console.error('HerbaGuard view error:', error.name, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="rounded-lg border border-line bg-surface p-6">
          <h2 className="text-lg font-semibold">Something went wrong</h2>
          <p className="mt-2 text-sm text-muted">
            This view could not be displayed. Please reload the page. If the problem continues, the
            information on this page should not be relied upon.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            className="mt-4 rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-900"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
