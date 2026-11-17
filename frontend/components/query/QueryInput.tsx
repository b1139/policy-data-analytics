"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { ArrowRight, RefreshCw, AlertCircle, Sparkles, CornerDownLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface QueryInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string) => void | Promise<void>;
  isLoading?: boolean;
  error?: string | null;
  placeholder?: string;
  maxLength?: number;
  minLength?: number;
  disabled?: boolean;
  className?: string;
}

const DEFAULT_PLACEHOLDER =
  "Ask a policy or economic question about Singapore, e.g., 'Analyse employment trends in tech 2020-2024'...";

export function QueryInput({
  value,
  onChange,
  onSubmit,
  isLoading = false,
  error: externalError = null,
  placeholder = DEFAULT_PLACEHOLDER,
  maxLength = 2000,
  minLength = 10,
  disabled = false,
  className,
}: QueryInputProps) {
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isShaking, setIsShaking] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea up to max 4 lines (~120px)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const minHeight = 84; // ~3 lines
    const maxHeight = 128; // ~4-5 lines max
    const computedHeight = Math.max(minHeight, Math.min(el.scrollHeight, maxHeight));
    el.style.height = `${computedHeight}px`;
  }, [value]);

  // Clear validation error when user edits
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const nextVal = e.target.value;
    if (nextVal.length <= maxLength) {
      onChange(nextVal);
      if (validationError && nextVal.trim().length >= minLength) {
        setValidationError(null);
      }
    }
  };

  const triggerShake = useCallback(() => {
    setIsShaking(true);
    const timer = setTimeout(() => setIsShaking(false), 500);
    return () => clearTimeout(timer);
  }, []);

  const handleValidateAndSubmit = useCallback(
    (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      if (isLoading || disabled) return;

      const trimmed = value.trim();
      if (!trimmed || trimmed.length < minLength) {
        setValidationError(`Please enter a query (minimum ${minLength} characters)`);
        triggerShake();
        if (textareaRef.current) {
          textareaRef.current.focus();
        }
        return;
      }

      setValidationError(null);
      onSubmit(trimmed);
    },
    [value, isLoading, disabled, minLength, onSubmit, triggerShake]
  );

  // Ctrl+Enter or Cmd+Enter keyboard shortcut
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleValidateAndSubmit();
    }
  };

  const displayedError = validationError || externalError;
  const charCount = value.length;
  const isNearLimit = charCount >= maxLength * 0.9;
  const isOverLimit = charCount >= maxLength;

  return (
    <form
      onSubmit={handleValidateAndSubmit}
      className={cn("w-full space-y-2", className)}
      noValidate
    >
      <div
        className={cn(
          "relative rounded-xl border bg-white shadow-sm transition-all duration-200 focus-within:shadow-md",
          displayedError
            ? "border-rose-400 focus-within:border-rose-500 focus-within:ring-2 focus-within:ring-rose-200"
            : "border-slate-300 focus-within:border-sg-blue focus-within:ring-2 focus-within:ring-sg-blue/20",
          isShaking && "animate-shake border-rose-500",
          (disabled || isLoading) && "bg-slate-50/70 opacity-90 cursor-not-allowed"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          rows={3}
          aria-label="Ask Me The Stats"
          aria-invalid={!!displayedError}
          aria-describedby={displayedError ? "query-error-message" : undefined}
          className={cn(
            "w-full resize-none bg-transparent p-4 pb-2 text-sm md:text-base leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:text-slate-500"
          )}
        />

        {/* Action bar inside query box */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 px-4 pb-3 pt-1 border-t border-slate-100/80 bg-slate-50/40 rounded-b-xl">
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span className="hidden md:inline-flex items-center gap-1 font-mono text-[11px] text-slate-400 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
              <CornerDownLeft className="h-3 w-3" />
              Ctrl+Enter to submit
            </span>
            <span
              className={cn(
                "font-mono text-[11px]",
                isOverLimit
                  ? "text-rose-600 font-semibold"
                  : isNearLimit
                    ? "text-amber-600 font-medium"
                    : "text-slate-400"
              )}
            >
              {charCount} / {maxLength}
            </span>
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button
              type="submit"
              variant="sg"
              size="default"
              disabled={disabled || isLoading || value.trim().length === 0}
              className={cn(
                "gap-2 px-5 font-semibold text-xs md:text-sm shadow-sm transition-all",
                isLoading && "opacity-90"
              )}
            >
              {isLoading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin text-white" />
                  <span>Submitting Query...</span>
                </>
              ) : (
                <>
                  <span>Run Analysis</span>
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Error alert display */}
      {displayedError && (
        <div
          id="query-error-message"
          role="alert"
          className="flex items-center gap-2 p-3 text-xs md:text-sm rounded-lg bg-rose-50 text-rose-700 border border-rose-200 animate-in fade-in slide-in-from-top-1 duration-150"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
          <span className="font-medium">{displayedError}</span>
        </div>
      )}
    </form>
  );
}
