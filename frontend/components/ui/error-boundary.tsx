"use client";

import { AlertTriangle } from "lucide-react";
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error boundary wrapper. Catches render errors in children
 * and shows a "Try Again" recovery UI.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
          <AlertTriangle size={48} className="text-boz-danger mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Something went wrong
          </h3>
          <p className="text-sm text-boz-neutral mb-4 max-w-sm">
            {this.props.fallbackMessage ||
              this.state.error?.message ||
              "An unexpected error occurred."}
          </p>
          <button
            onClick={this.handleRetry}
            className="min-h-[44px] px-6 py-2 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
