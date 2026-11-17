import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { AnalysisStatus } from "@/types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDate(dateInput: string | number | Date | null | undefined): string {
  if (!dateInput) return "—";
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return String(dateInput);
    return new Intl.DateTimeFormat("en-SG", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return String(dateInput);
  }
}

export interface StatusMeta {
  label: string;
  color: string;
  textColor: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
}

export function formatStatus(status: AnalysisStatus | string | null | undefined): StatusMeta {
  const normalized = (status || "PENDING").toUpperCase();

  switch (normalized) {
    case "DONE":
    case "COMPLETED":
    case "SUCCESS":
      return {
        label: "Completed",
        color: "#16A34A",
        textColor: "#16A34A",
        bgClass: "bg-emerald-50 dark:bg-emerald-950/40",
        textClass: "text-emerald-700 dark:text-emerald-400",
        borderClass: "border-emerald-200 dark:border-emerald-800",
      };
    case "RUNNING":
    case "IN_PROGRESS":
      return {
        label: "Running",
        color: "#F4A201",
        textColor: "#D97706",
        bgClass: "bg-amber-50 dark:bg-amber-950/40",
        textClass: "text-amber-700 dark:text-amber-400",
        borderClass: "border-amber-200 dark:border-amber-800",
      };
    case "FAILED":
    case "ERROR":
      return {
        label: "Failed",
        color: "#DC2626",
        textColor: "#DC2626",
        bgClass: "bg-red-50 dark:bg-red-950/40",
        textClass: "text-red-700 dark:text-red-400",
        borderClass: "border-red-200 dark:border-red-800",
      };
    case "PENDING":
    default:
      return {
        label: "Pending",
        color: "#6B7280",
        textColor: "#4B5563",
        bgClass: "bg-slate-100 dark:bg-slate-800/60",
        textClass: "text-slate-700 dark:text-slate-300",
        borderClass: "border-slate-200 dark:border-slate-700",
      };
  }
}

export function formatUserFriendlyError(error: string | null | undefined): string {
  if (!error) return "An unexpected error occurred during execution.";

  const raw = String(error).trim();

  // If error has a python traceback, strip it down to the final meaningful sentence
  if (raw.includes("Traceback (most recent call last):")) {
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    const lastLine = lines[lines.length - 1] || "";
    const cleanMsg = lastLine.includes(": ") ? lastLine.split(": ").slice(1).join(": ") : lastLine;
    return cleanMsg || "Execution encountered an issue. Please try re-running.";
  }

  // Common pattern replacements
  const lower = raw.toLowerCase();
  if (lower.includes("all configured llm providers failed") || lower.includes("allprovidersfailed")) {
    return "AI service temporarily unavailable: both primary and backup language models could not be reached. Please re-run the analysis.";
  }
  if (lower.includes("rate limit") || lower.includes("429") || lower.includes("resource exhausted") || lower.includes("quota exceeded")) {
    return "The AI service is currently busy or rate-limited. Please retry in a few moments.";
  }
  if (lower.includes("timeout") || lower.includes("timed out") || lower.includes("504") || lower.includes("502")) {
    return "Service connection timed out while processing your request. Please try re-running.";
  }
  if (
    lower.includes("extraction failed") ||
    lower.includes("is empty") ||
    lower.includes("no datasets retrieved") ||
    lower.includes("no matching datasets")
  ) {
    if (raw.includes("for '")) {
      const match = raw.match(/for '([^']+)'/);
      if (match && match[1]) {
        return `Data extraction could not retrieve official records for '${match[1]}'. Try re-running or resolving with AI assistance.`;
      }
    }
    return "Data extraction could not retrieve official records for the requested parameters. Try re-running or resolving with AI assistance.";
  }

  // Remove [router] or [gemini] bracket prefixes if present
  let sanitized = raw.replace(/^\[(router|gemini|bedrock|openai|anthropic)\]\s*/i, "");
  if (sanitized.length > 220) {
    sanitized = sanitized.slice(0, 217) + "...";
  }
  return sanitized;
}
