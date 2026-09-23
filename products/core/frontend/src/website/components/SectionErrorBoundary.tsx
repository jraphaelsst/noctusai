/**
 * Isolates a render failure to ONE home section or product chapter.
 *
 * Without it, a single component throwing during render (e.g. the pricing
 * card on an unexpected API shape, 2026-09-23) unmounts the whole React root.
 * That wipes the prerendered HTML and leaves visitors on a blank page, even
 * though every other section was fine.
 *
 * On error the section renders nothing, and the error is reported with
 * `console.error` naming the section. This is deliberately not silent: the
 * failure stays visible in the console and in any error tracking wired to it.
 * Server-side render errors are NOT caught here: `renderToString` throws, so
 * the build fails loudly, which is what we want.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  /** Section key or product slug, used in the error report. */
  name: string;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export class SectionErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[website] section "${this.props.name}" failed to render and was hidden`, error, info.componentStack);
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}
