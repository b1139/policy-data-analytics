"use client";

import React from "react";
import {
  TrendingUp,
  TrendingDown,
  Calendar,
  Percent,
  Database,
  Activity,
  Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { KeyMetric, StatsResult } from "@/types";

interface StatsCardsProps {
  stats?: StatsResult | null;
  loading?: boolean;
  noData?: boolean;
}

function hasStatsData(stats: StatsResult | null | undefined): boolean {
  if (!stats || typeof stats !== "object") return false;
  const s = stats as Record<string, unknown>;
  if (s.error) return false;
  if (Array.isArray(s.key_metrics) && s.key_metrics.length > 0) return true;
  if (typeof s.data_points_count === "number") return s.data_points_count > 0;
  if (typeof s.total_records === "number") return s.total_records > 0;
  const summary = s.summary as Record<string, unknown> | undefined;
  if (summary && typeof summary === "object") {
    return !summary.error && Number(summary.count ?? 0) > 0;
  }
  return Object.keys(s).length > 0 && Boolean(s.trend || s.trend_direction || s.cagr);
}

function fmt(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return Math.round(n).toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Legacy fallback for analyses stored before `key_metrics` existed. Uses only reliable fields. */
function deriveFallbackMetrics(stats: StatsResult): KeyMetric[] {
  const out: KeyMetric[] = [];
  const s = stats as Record<string, unknown>;
  const sm = (s.summary && typeof s.summary === "object" ? s.summary : {}) as Record<string, unknown>;
  const num = (v: unknown) => (typeof v === "number" && isFinite(v) ? v : null);

  const trend = s.trend as Record<string, unknown> | string | undefined;
  const dir =
    typeof trend === "string"
      ? trend
      : String((trend as Record<string, unknown> | undefined)?.overall_trend ?? s.trend_direction ?? "");
  if (dir) {
    const d = dir.toLowerCase();
    out.push({
      id: "trend",
      label: "Trend Direction",
      value: d.includes("incr") ? "Increasing" : d.includes("decr") ? "Decreasing" : "Stable",
      caption: "Statistical trend over the period",
      tone: d.includes("incr") ? "positive" : d.includes("decr") ? "negative" : "neutral",
      icon: d.includes("decr") ? "trend-down" : "trend",
    });
  }
  const mean = num(sm.mean);
  if (mean !== null) out.push({ id: "mean", label: "Average Value", value: fmt(mean), caption: "Mean across observations", icon: "activity" });
  const max = num(sm.max);
  if (max !== null) out.push({ id: "max", label: "Highest Value", value: fmt(max), caption: `Lowest: ${num(sm.min) !== null ? fmt(num(sm.min)!) : "n/a"}`, icon: "calendar" });
  const count = num(sm.count) ?? num(s.data_points_count) ?? num(s.total_records);
  if (count !== null && count > 0) out.push({ id: "count", label: "Observations", value: count.toLocaleString(), caption: "Official records analysed", icon: "database" });
  return out.slice(0, 4);
}

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  trend: TrendingUp,
  "trend-down": TrendingDown,
  calendar: Calendar,
  percent: Percent,
  database: Database,
  activity: Activity,
};

const TONE = {
  positive: { border: "border-l-emerald-500", text: "text-emerald-600" },
  negative: { border: "border-l-rose-500", text: "text-rose-600" },
  neutral: { border: "border-l-blue-600", text: "text-slate-900" },
} as const;

export function StatsCards({ stats, loading = false, noData = false }: StatsCardsProps) {
  const grid = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4";

  if (noData || (!loading && stats && !hasStatsData(stats))) {
    return (
      <div className={grid}>
        {["Latest Value", "Change", "Peak Period", "Observations"].map((label) => (
          <Card key={label} className="p-4 bg-white border-slate-200 shadow-sm border-l-4 border-l-slate-300">
            <CardContent className="p-0 space-y-1">
              <div className="text-xs text-muted-foreground font-medium">{label}</div>
              <div className="pt-1">
                <span className="text-2xl font-bold tracking-tight text-slate-400">No Data</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (loading || !stats) {
    return (
      <div className={grid}>
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="p-4 border-slate-200 bg-white">
            <div className="space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-20" />
              <Skeleton className="h-3 w-32" />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  const metrics: KeyMetric[] =
    Array.isArray(stats.key_metrics) && stats.key_metrics.length > 0
      ? stats.key_metrics
      : deriveFallbackMetrics(stats);

  return (
    <div className={grid}>
      {metrics.map((m) => {
        const tone = TONE[(m.tone as keyof typeof TONE) || "neutral"] ?? TONE.neutral;
        const Icon = ICONS[m.icon || "activity"] ?? Activity;
        return (
          <Card key={m.id} className={`p-4 bg-white border-slate-200 shadow-sm border-l-4 ${tone.border}`}>
            <CardContent className="p-0 space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                <span className="truncate">{m.label}</span>
                <span className="flex items-center gap-1 shrink-0">
                  {m.source === "llm" && <Sparkles className="h-3 w-3 text-amber-500" aria-label="AI-selected" />}
                  <Icon className="h-4 w-4" />
                </span>
              </div>
              <div className="pt-1">
                <span className={`text-2xl font-bold tracking-tight ${tone.text}`} title={m.value}>
                  {m.value}
                </span>
              </div>
              {m.caption && (
                <p className="text-[11px] text-muted-foreground truncate pt-0.5" title={m.caption}>
                  {m.caption}
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
