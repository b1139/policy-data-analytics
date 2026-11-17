"use client";

import React, { useState } from "react";
import { Sparkles, Copy, Check, ExternalLink, Quote } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Citation } from "@/types";
import { NoData } from "@/components/ui/no-data";

interface InsightPanelProps {
  insights?: string | null;
  citations?: Citation[] | null;
  loading?: boolean;
  noData?: boolean;
}

/** Render **bold** inline markup without needing a markdown dependency. */
function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold text-slate-900">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );
}

type Block =
  | { kind: "heading"; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "para"; text: string };

const BULLET_RE = /^\s*(?:[-*•]|\d+[.)])\s+/;

function parseInsights(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (BULLET_RE.test(line)) {
      const item = line.replace(BULLET_RE, "");
      const last = blocks[blocks.length - 1];
      if (last?.kind === "bullets") last.items.push(item);
      else blocks.push({ kind: "bullets", items: [item] });
    } else if (/^#{1,6}\s+/.test(line)) {
      blocks.push({ kind: "heading", text: line.replace(/^#{1,6}\s+/, "") });
    } else if (/^\*\*[^*]+\*\*:?$/.test(line)) {
      blocks.push({ kind: "heading", text: line.replace(/\*\*/g, "").replace(/:$/, "") });
    } else {
      blocks.push({ kind: "para", text: line });
    }
  }
  return blocks;
}

export function InsightPanel({
  insights,
  citations = [],
  loading = false,
  noData = false,
}: InsightPanelProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!insights) return;
    try {
      await navigator.clipboard.writeText(insights);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
      const textarea = document.createElement("textarea");
      textarea.value = insights;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading) {
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b">
          <div className="flex items-center justify-between">
            <div className="space-y-1.5">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
            <Skeleton className="h-8 w-24" />
          </div>
        </CardHeader>
        <CardContent className="p-5 space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-[95%]" />
          <Skeleton className="h-4 w-[90%]" />
          <div className="pt-2">
            <Skeleton className="h-16 w-full rounded-md" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (noData) {
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b">
          <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Synthesis &amp; Policy Insights
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6">
          <NoData message="No data was found for this query, so no insights were generated." />
        </CardContent>
      </Card>
    );
  }

  if (!insights) {
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b">
          <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-sg-amber" />
            Synthesis & Policy Insights
          </CardTitle>
          <CardDescription className="text-xs">
            Synthesized by multi-agent analysis graph
          </CardDescription>
        </CardHeader>
        <CardContent className="p-8 text-center text-muted-foreground text-xs">
          Awaiting agent synthesis. Insights will appear once extraction and statistical modeling conclude.
        </CardContent>
      </Card>
    );
  }

  const blocks = parseInsights(insights);

  return (
    <Card className="border-slate-200 shadow-sm bg-white">
      <CardHeader className="p-5 pb-3 border-b flex flex-row items-center justify-between gap-4">
        <div>
          <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Synthesis & Policy Insights
          </CardTitle>
          <CardDescription className="text-xs">
            Rigorous analysis grounded on verified government statistical datasets
          </CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleCopy}
          className="gap-1.5 text-xs shrink-0 h-8"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-emerald-700 font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy Insight</span>
            </>
          )}
        </Button>
      </CardHeader>

      <CardContent className="p-5 space-y-4">
        <div className="space-y-3 text-sm text-slate-700 leading-relaxed">
          {blocks.map((block, idx) => {
            if (block.kind === "heading") {
              const isPolicy = /policy|implication|recommend/i.test(block.text);
              return (
                <h4
                  key={idx}
                  className={`pt-2 text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                    isPolicy ? "text-blue-700" : "text-slate-500"
                  }`}
                >
                  {isPolicy && <Quote className="h-3.5 w-3.5" />}
                  {block.text}
                </h4>
              );
            }
            if (block.kind === "bullets") {
              return (
                <ul key={idx} className="space-y-2">
                  {block.items.map((item, i) => (
                    <li key={i} className="flex gap-2.5 items-start">
                      <span className="mt-2 h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />
                      <span className="text-slate-800">{renderInline(item)}</span>
                    </li>
                  ))}
                </ul>
              );
            }
            const isAnswer = /^\*\*answer/i.test(block.text);
            return (
              <p
                key={idx}
                className={
                  isAnswer
                    ? "p-3 rounded-lg bg-blue-50/60 border border-blue-200/70 text-slate-900 font-medium"
                    : "text-slate-800"
                }
              >
                {renderInline(block.text)}
              </p>
            );
          })}
        </div>

        {/* Inline Source Citations Badge Bar */}
        {citations && citations.length > 0 && (
          <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Cited Sources:
            </span>
            {citations.map((c, i) => {
              let targetUrl = c.url?.trim() || "";
              const title = (c.title || "").toLowerCase();
              const src = (c.source || "").toLowerCase();

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
                  key={i}
                  href={targetUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex"
                  title={`Open official statistics: ${targetUrl}`}
                >
                  <Badge
                    variant="outline"
                    className="bg-slate-50 hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-sg-blue border-slate-200 text-[11px] py-0.5 px-2 gap-1.5 cursor-pointer transition-colors shadow-2xs"
                  >
                    <span className="font-medium">{c.source}</span>
                    {c.title && <span className="text-slate-400 font-normal max-w-[200px] truncate">({c.title})</span>}
                    <ExternalLink className="h-2.5 w-2.5 text-blue-600 shrink-0" />
                  </Badge>
                </a>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
