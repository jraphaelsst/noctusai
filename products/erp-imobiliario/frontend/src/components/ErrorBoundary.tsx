import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error Boundary component for catching and handling React errors.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary>
 *   <YourComponent />
 * </ErrorBoundary>
 * ```
 *
 * With custom fallback:
 * ```tsx
 * <ErrorBoundary fallback={<CustomErrorUI />}>
 *   <YourComponent />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console in development
    console.error("ErrorBoundary caught an error:", error, errorInfo);

    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo);

    // Report to Sentry if available
    if (typeof window !== "undefined" && (window as any).Sentry) {
      (window as any).Sentry.captureException(error, {
        extra: {
          componentStack: errorInfo.componentStack,
        },
      });
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center">
          <div className="flex items-center justify-center w-16 h-16 mb-6 rounded-full bg-destructive/10">
            <AlertTriangle className="w-8 h-8 text-destructive" />
          </div>

          <h2 className="text-2xl font-semibold mb-2">Algo deu errado</h2>

          <p className="text-muted-foreground mb-6 max-w-md">
            Ocorreu um erro inesperado. Por favor, tente novamente ou recarregue
            a página.
          </p>

          {process.env.NODE_ENV === "development" && this.state.error && (
            <div className="mb-6 p-4 bg-muted rounded-lg text-left max-w-lg overflow-auto">
              <p className="font-mono text-sm text-destructive">
                {this.state.error.message}
              </p>
              {this.state.error.stack && (
                <pre className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap">
                  {this.state.error.stack}
                </pre>
              )}
            </div>
          )}

          <div className="flex gap-4">
            <Button variant="outline" onClick={this.handleReset}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Tentar novamente
            </Button>
            <Button onClick={this.handleReload}>Recarregar página</Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Higher-order component to wrap a component with ErrorBoundary.
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  fallback?: ReactNode
) {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}
