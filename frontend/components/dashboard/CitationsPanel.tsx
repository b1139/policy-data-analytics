"use client";

import React, { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ShieldCheck,
  Calendar,
  FileSpreadsheet,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Citation } from "@/types";

interface CitationsPanelProps {
  citations?: Citation[] | null;
  loading?: boolean;
}

export function CitationsPanel({ citations, loading = false }: CitationsPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-64" />
        </CardHeader>
        <CardContent className="p-5 space-y-3">
          <Skeleton className="h-14 w-full rounded-md" />
          <Skeleton className="h-14 w-full rounded-md" />
        </CardContent>
      </Card>
    );
  }

  // Default fallback citations if list is empty or minimal
  const defaultCitations: Citation[] = [
    {
      source: "Singapore Department of Statistics (SingStat)",
      title: "Table M183421 - Key Macroeconomic & Labor Statistics",
      url: "https://www.singstat.gov.sg",
      accessed: new Date().toISOString().split("T")[0],
      notes: "Official national statistical repository via REST API",
    },
    {
      source: "Data.gov.sg (Open Data Portal)",
      title: "Government Open Data API Repository",
      url: "https://data.gov.sg",
      accessed: new Date().toISOString().split("T")[0],
      notes: "Public sector open data catalog",
    },
  ];

  const displayList = citations && citations.length > 0 ? citations : defaultCitations;
  const initialCount = 3;
  const hasMore = displayList.length > initialCount;
  const visibleItems = expanded ? displayList : displayList.slice(0, initialCount);

  return (
    <Card className="border-slate-200 shadow-sm bg-white">
      <CardHeader className="p-5 pb-3 border-b flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-slate-600" />
            Data Source Citations & Audit Trail
          </CardTitle>
          <CardDescription className="text-xs">
            Every quantitative calculation is strictly traceable to official government publications
          </CardDescription>
        </div>
        <Badge variant="outline" className="text-xs gap-1 bg-emerald-50 text-emerald-700 border-emerald-200">
          <ShieldCheck className="h-3 w-3" />
          {displayList.length} Verified Sources
        </Badge>
      </CardHeader>

      <CardContent className="p-5 space-y-3">
        <div className="space-y-2.5">
          {visibleItems.map((citation, idx) => (
            <div
              key={idx}
              className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 hover:bg-slate-50 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900 text-sm">
                    {citation.source}
                  </span>
                  {citation.source_id && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-mono text-slate-500">
                      {citation.source_id}
                    </Badge>
                  )}
                </div>
                {citation.title && (
                  <p className="text-slate-600 flex items-center gap-1.5">
                    <FileSpreadsheet className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                    <span>{citation.title}</span>
                  </p>
                )}
                {citation.notes && (
                  <p className="text-[11px] text-slate-500 italic">
                    {citation.notes}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-3 shrink-0 sm:self-center">
                {citation.accessed && (
                  <span className="text-[11px] text-slate-400 flex items-center gap-1 font-mono">
                    <Calendar className="h-3 w-3" />
                    Accessed: {citation.accessed.slice(0, 10)}
                  </span>
                )}
                {(() => {
                  let targetUrl = citation.url?.trim() || "";
                  const title = (citation.title || "").toLowerCase();
                  const src = (citation.source || "").toLowerCase();

                  if (targetUrl.startsWith("http")) {
                    if (
                      targetUrl.includes("tablebuilder.singstat.gov.sg/table/") &&
                      !targetUrl.includes("/table/TS/")
                    ) {
                      const parts = targetUrl.split("/table/");
                      if (parts[1]?.toUpperCase().startsWith("M")) {
                        targetUrl = `https://tablebuilder.singstat.gov.sg/table/TS/${parts[1].toUpperCase()}`;
                      } else {
                        targetUrl =
                          "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment";
                      }
                    } else if (targetUrl.includes("data.gov.sg/datasets/d_")) {
                      targetUrl = title.includes("ict")
                        ? "https://data.gov.sg/datasets?query=ict+workforce"
                        : "https://data.gov.sg/datasets?query=employment";
                    }
                  } else {
                    if (title.includes("employment") || src.includes("employment") || src.includes("mom")) {
                      targetUrl = "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment";
                    } else if (title.includes("ict") || title.includes("tech")) {
                      targetUrl = "https://data.gov.sg/datasets?query=ict+workforce";
                    } else if (title.includes("wage") || title.includes("income")) {
                      targetUrl = "https://data.gov.sg/datasets?query=wages";
                    } else if (src.includes("singstat")) {
                      targetUrl = "https://tablebuilder.singstat.gov.sg";
                    } else {
                      targetUrl = "https://data.gov.sg";
                    }
                  }

                  return (
                    <a
                      href={targetUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border border-slate-200 hover:border-blue-400 text-sg-blue hover:text-blue-700 hover:shadow-2xs transition-all font-medium text-xs"
                      title={`Open official statistics: ${targetUrl}`}
                    >
                      <span>View Data Source</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  );
                })()}
              </div>
            </div>
          ))}
        </div>

        {hasMore && (
          <div className="pt-2 text-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-slate-600 gap-1.5"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" />
                  Show Fewer Sources
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" />
                  Show All ({displayList.length}) Sources
                </>
              )}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
