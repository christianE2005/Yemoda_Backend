import { Component, type ReactNode, type ErrorInfo } from 'react';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleGoHome = () => {
    window.location.href = '/dashboard';
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center max-w-sm">
            <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-5 h-5 text-destructive" />
            </div>
            <h2 className="text-lg font-semibold text-foreground mb-1">Algo salió mal</h2>
            <p className="text-sm text-muted-foreground mb-6">
              Ocurrió un error inesperado. Puedes intentar recargar el componente o volver al inicio.
            </p>
            {this.state.error && (
              <p className="text-xs text-muted-foreground bg-muted rounded-md px-3 py-2 mb-6 font-mono break-all">
                {this.state.error.message}
              </p>
            )}
            <div className="flex items-center gap-3 justify-center">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 bg-primary hover:bg-primary-hover text-primary-foreground rounded-md text-sm font-medium transition-colors inline-flex items-center gap-2"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reintentar
              </button>
              <button
                onClick={this.handleGoHome}
                className="px-4 py-2 bg-secondary hover:bg-accent text-foreground rounded-md text-sm font-medium transition-colors inline-flex items-center gap-2"
              >
                <Home className="w-3.5 h-3.5" />
                Ir al inicio
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
