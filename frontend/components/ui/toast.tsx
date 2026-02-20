"use client";

/**
 * Toast notification system.
 *
 * Provides a context-based toast system with auto-dismiss and slide-in animation.
 * Three variants: success (green), info (blue), warning (amber).
 *
 * Usage:
 *   const { showToast } = useToast();
 *   showToast({ variant: "success", title: "Trade approved!", message: "..." });
 */

import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ─── Types ───

export type ToastVariant = "success" | "info" | "warning";

export interface ToastData {
  variant: ToastVariant;
  title: string;
  message?: string;
  duration?: number; // ms, default 4000
}

interface ToastEntry extends ToastData {
  id: number;
  exiting: boolean;
}

// ─── Variant Styles ───

const VARIANT_CONFIG: Record<
  ToastVariant,
  { icon: LucideIcon; bg: string; border: string; iconColor: string }
> = {
  success: {
    icon: CheckCircle2,
    bg: "bg-emerald-50",
    border: "border-emerald-300",
    iconColor: "text-emerald-600",
  },
  info: {
    icon: Info,
    bg: "bg-blue-50",
    border: "border-blue-300",
    iconColor: "text-blue-600",
  },
  warning: {
    icon: AlertTriangle,
    bg: "bg-amber-50",
    border: "border-amber-300",
    iconColor: "text-amber-600",
  },
};

// ─── Context ───

interface ToastContextValue {
  showToast: (toast: ToastData) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

// ─── Toast Item ───

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastEntry;
  onDismiss: (id: number) => void;
}) {
  const { icon: Icon, bg, border, iconColor } = VARIANT_CONFIG[toast.variant];

  return (
    <div
      className={`
        flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg
        ${bg} ${border}
        ${toast.exiting ? "animate-toast-out" : "animate-toast-in"}
      `}
      role="alert"
    >
      <Icon size={22} className={`${iconColor} flex-shrink-0 mt-0.5`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">{toast.title}</p>
        {toast.message && (
          <p className="text-xs text-gray-600 mt-0.5">{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
      >
        <X size={16} />
      </button>
    </div>
  );
}

// ─── Provider ───

const DEFAULT_DURATION = 4000;
const EXIT_ANIMATION_MS = 300;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const idCounter = useRef(0);

  const dismiss = useCallback((id: number) => {
    // Start exit animation
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)),
    );
    // Remove after animation completes
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, EXIT_ANIMATION_MS);
  }, []);

  const showToast = useCallback(
    (toast: ToastData) => {
      const id = ++idCounter.current;
      setToasts((prev) => [...prev, { ...toast, id, exiting: false }]);

      // Auto-dismiss
      const duration = toast.duration ?? DEFAULT_DURATION;
      setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}

      {/* Toast container — fixed at top center */}
      {toasts.length > 0 && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 w-[90vw] max-w-md">
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}
