import { Component, type ReactNode } from 'react';

import { Button } from './ui';

interface State { error: Error | null }

/** Keeps a rendering fault in one page from blanking the whole console. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error('Interface error', error);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="state" role="alert">
        <h3>This page failed to display</h3>
        <p>The rest of RAAHAT still works. Reload to try again; if it keeps happening, report it with the time.</p>
        <p className="xs faint mono">{this.state.error.message}</p>
        <div className="row"><Button onClick={() => this.setState({ error: null })}>Try again</Button><Button variant="primary" onClick={() => window.location.reload()}>Reload</Button></div>
      </div>
    );
  }
}
