import { Component, type ReactNode } from 'react'
import { log } from '../log'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  componentDidCatch(error: Error) { log.error('UI', error.message) }
  render() {
    if (this.state.error) return <div className="pane-empty" role="alert"><h2>This view could not be displayed.</h2><p>Check the transcript for details, then retry.</p><button className="btn-run" onClick={() => this.setState({ error: false })}>Retry view</button></div>
    return this.props.children
  }
}
