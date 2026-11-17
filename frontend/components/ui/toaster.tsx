"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "destructive" | "warning";

export interface ToastMessage {
  id: string;
  title?: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastContextType {
  toasts: ToastMessage[];
  toast: (options: Omit<ToastMessage, "id">) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

let globalToastHandler: ((options: Omit<ToastMessage, "id">) => void) | null = null;

export function toast(options: Omit<ToastMessage, "id">) {
  if (globalToastHandler) {
    globalToastHandler(options);
  } else {
    console.log(`[Toast ${options.variant || "default"}]:`, options.title, options.description);
  }
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    ({ title, description, variant = "default", duration = 4000 }: Omit<ToastMessage, "id">) => {
      const id = Math.random().toString(36).substring(2, 9);
      const newToast: ToastMessage = { id, title, description, variant, duration };

      setToasts((prev) => [...prev, newToast]);

      if (duration > 0) {
        setTimeout(() => {
          dismiss(id);
        }, duration);
      }
    },
    [dismiss]
  );

  useEffect(() => {
    globalToastHandler = addToast;
    return () => {
      globalToastHandler = null;
    };
  }, [addToast]);

  return (
    <ToastContext.Provider value={{ toasts, toast: addToast, dismiss }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      toasts: [],
      toast,
      dismiss: () => {},
    };
  }
  return context;
}

export function Toaster() {
  const { toasts, dismiss } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none"
    >
      {toasts.map((t) => {
        const icons = {
          default: <Info className="h-5 w-5 text-sg-blue shrink-0" />,
          success: <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />,
          destructive: <AlertCircle className="h-5 w-5 text-rose-500 shrink-0" />,
          warning: <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />,
        };

        const borders = {
          default: "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900",
          success: "border-emerald-200 dark:border-emerald-800 bg-emerald-50/90 dark:bg-emerald-950/90",
          destructive: "border-rose-200 dark:border-rose-800 bg-rose-50/90 dark:bg-rose-950/90",
          warning: "border-amber-200 dark:border-amber-800 bg-amber-50/90 dark:bg-amber-950/90",
        };

        return (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-3 p-4 rounded-lg border shadow-lg transition-all animate-in fade-in slide-in-from-bottom-2 duration-200",
              borders[t.variant || "default"]
            )}
          >
            {icons[t.variant || "default"]}
            <div className="flex-1 text-sm">
              {t.title && <p className="font-semibold text-foreground">{t.title}</p>}
              {t.description && <p className="text-muted-foreground mt-0.5">{t.description}</p>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-muted-foreground hover:text-foreground transition-colors p-1 -mr-1 -mt-1 rounded focus:outline-none"
              aria-label="Close toast"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
