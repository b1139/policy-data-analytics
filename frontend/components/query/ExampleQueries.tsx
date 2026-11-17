"use client";

import React from "react";
import { Sparkles, TrendingUp, Users, Factory, Globe2, Wallet, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ExampleQueryItem {
  query: string;
  category: string;
  icon?: React.ComponentType<{ className?: string }>;
  badgeColor?: string;
}

export const CATEGORIZED_EXAMPLE_QUERIES: ExampleQueryItem[] = [
  {
    category: "Population & Demographics",
    query: "Analyze Singapore population growth trends, total fertility rate (TFR), marriage rates, and life expectancy from 2018 to 2024",
    icon: Users,
    badgeColor: "bg-blue-100 text-blue-800 border-blue-200",
  },
  {
    category: "Macroeconomic Growth",
    query: "Evaluate Singapore's real GDP growth trajectory, annual growth rates, and economic cycles over the last 6 years (2018-2024)",
    icon: TrendingUp,
    badgeColor: "bg-emerald-100 text-emerald-800 border-emerald-200",
  },
  {
    category: "Industry Sectors",
    query: "Compare GDP growth rates and sectoral economic contribution across major Singapore industries: Manufacturing, Finance, ICT, and Wholesale Trade",
    icon: Factory,
    badgeColor: "bg-amber-100 text-amber-800 border-amber-200",
  },
  {
    category: "Trade & Investments",
    query: "Examine Singapore external trade performance, Non-Oil Domestic Exports (NODX) growth, and foreign direct investment (FDI) inflows (2020-2024)",
    icon: Globe2,
    badgeColor: "bg-indigo-100 text-indigo-800 border-indigo-200",
  },
  {
    category: "Household Income",
    query: "Analyze median monthly household income from work, wage percentiles, and Gini coefficient in Singapore over the last 3 years",
    icon: Wallet,
    badgeColor: "bg-teal-100 text-teal-800 border-teal-200",
  },
  {
    category: "Aging vs Youth",
    query: "Assess aging population trends versus youth demographic growth in Singapore: elderly (65+) dependency ratio compared with youth cohort (2018-2024)",
    icon: Hourglass,
    badgeColor: "bg-purple-100 text-purple-800 border-purple-200",
  },
];

export const DEFAULT_EXAMPLE_QUERIES = CATEGORIZED_EXAMPLE_QUERIES.map((item) => item.query) as readonly string[];

export interface ExampleQueriesProps {
  onSelect: (query: string) => void;
  disabled?: boolean;
  queries?: readonly string[] | string[];
  className?: string;
}

export function ExampleQueries({
  onSelect,
  disabled = false,
  queries,
  className,
}: ExampleQueriesProps) {
  // If custom queries string array is provided, display plain chips
  if (queries && queries.length > 0) {
    return (
      <div className={cn("space-y-2.5", className)}>
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
          <span>Try Example Policy Queries:</span>
        </div>

        <div className="flex flex-wrap gap-2">
          {queries.map((exampleQuery, index) => (
            <button
              key={index}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(exampleQuery)}
              className={cn(
                "group inline-flex items-center gap-1.5 text-left text-xs font-medium px-3.5 py-1.5 rounded-full transition-all duration-150",
                "border border-slate-200 bg-slate-50/80 text-slate-700 shadow-sm",
                "hover:border-sg-blue/40 hover:bg-blue-50/70 hover:text-sg-blue hover:shadow",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sg-blue focus-visible:ring-offset-1",
                "active:scale-[0.98]",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
              title={`Select: "${exampleQuery}"`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-sg-blue/50 group-hover:bg-sg-blue shrink-0 transition-colors" />
              <span>{exampleQuery}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600">
          <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
          <span>Recommended Policy Inquiry Benchmarks</span>
        </div>
        <span className="text-[11px] text-muted-foreground hidden sm:inline">
          Click any policy theme to auto-fill query
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {CATEGORIZED_EXAMPLE_QUERIES.map((item, index) => {
          const Icon = item.icon || Sparkles;
          return (
            <button
              key={index}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(item.query)}
              className={cn(
                "group relative text-left p-2.5 rounded-lg transition-all duration-150",
                "border border-slate-200 bg-slate-50/60 hover:bg-white hover:border-sg-blue/50 hover:shadow-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sg-blue focus-visible:ring-offset-1",
                "active:scale-[0.99]",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
              title={`Click to analyze: "${item.query}"`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border flex items-center gap-1", item.badgeColor)}>
                  <Icon className="h-3 w-3 shrink-0" />
                  {item.category}
                </span>
              </div>
              <p className="text-xs text-slate-700 font-medium group-hover:text-sg-blue transition-colors line-clamp-2 leading-snug">
                {item.query}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
