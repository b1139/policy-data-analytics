"use client";

import React, { useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  ArrowRight,
  Clock,
  RefreshCw,
  Search,
  FileQuestion,
  Activity,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatStatus, formatDate } from "@/lib/utils";
import { useToast } from "@/components/ui/toaster";
import { startAnalysis, listAnalyses } from "@/lib/api";
import { QueryInput } from "@/components/query/QueryInput";
import { ExampleQueries } from "@/components/query/ExampleQueries";
import { PolicyIndicatorsHub } from "@/components/dashboard/PolicyIndicatorsHub";
import type { AnalysisListItem } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const querySectionRef = useRef<HTMLDivElement>(null);

  // TanStack Query mutation to start multi-agent analysis
  const startMutation = useMutation({
    mutationFn: (queryText: string) => startAnalysis(queryText),
    onSuccess: (data) => {
      // Invalidate both recent and full analysis history
      queryClient.invalidateQueries({ queryKey: ["recent-analyses"] });
      queryClient.invalidateQueries({ queryKey: ["analyses"] });

      toast({
        title: "Analysis started — tracking in real time",
        description: `Analysis ID: ${data.analysis_id}. Initializing multi-agent pipeline...`,
        variant: "success",
      });
      router.push(`/dashboard/analysis/${data.analysis_id}`);
    },
    onError: (err: any) => {
      const errorMessage =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to trigger analysis. Please ensure the backend API is online.";

      toast({
        title: "Analysis Submission Failed",
        description: errorMessage,
        variant: "destructive",
      });
    },
  });

  // Query recent real analyses from backend database
  const { data: recentData, isLoading: recentLoading, refetch: refetchRecent } = useQuery({
    queryKey: ["recent-analyses"],
    queryFn: () => listAnalyses(0, 5),
    refetchOnMount: "always",
    staleTime: 5000,
  });

  const recentItems = recentData?.items || [];

  const handleSubmit = (submittedQuery: string) => {
    startMutation.mutate(submittedQuery);
  };

  const handleSelectExample = (exampleQuery: string, autoSubmit: boolean = false) => {
    setQuery(exampleQuery);
    if (querySectionRef.current) {
      querySectionRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (autoSubmit) {
      startMutation.mutate(exampleQuery);
    }
  };

  const errorMessage = startMutation.isError
    ? (startMutation.error as any)?.response?.data?.detail ||
      startMutation.error?.message ||
      "Failed to submit query. Please verify network connectivity."
    : null;

  return (
    <div className="container mx-auto p-4 md:p-8 max-w-6xl space-y-8">
      {/* Platform Header */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="sg" className="uppercase tracking-wider text-[10px] font-semibold">
            GovTech Singapore Standards
          </Badge>
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
            3 Multi-Agent Nodes Active
          </span>
        </div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900">
          Singapore Policy Data Analytics Platform
        </h1>
        <p className="text-sm md:text-base text-slate-600 max-w-3xl">
          Autonomous multi-agent intelligence for Singapore public policy. Live national economic &amp; demographic indicators, automated SingStat &amp; Data.gov.sg extraction, and inferential statistical modeling with verified citations.
        </p>
      </section>

      {/* 1. National Indicators & Policy Trends Dashboard Hub */}
      <PolicyIndicatorsHub onSelectQuery={(q) => handleSelectExample(q, false)} />

      {/* 2. Query Input & Autonomous Agent Console */}
      <div ref={querySectionRef} id="query-section">
        <Card className="border-slate-200 shadow-sm bg-white overflow-hidden">
          <div className="h-1.5 w-full bg-gradient-to-r from-sg-blue via-sky-500 to-sg-amber" />
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2 text-slate-900">
              <Sparkles className="h-5 w-5 text-sg-amber" />
              Ask Me The Stats — Policy Query Console
            </CardTitle>
            <CardDescription>
              Submit questions on Singapore GDP, population demographics, labor, trade, or household income. Autonomous ReAct agents orchestrate retrieval, modeling, and Plotly visualization.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <QueryInput
              value={query}
              onChange={setQuery}
              onSubmit={handleSubmit}
              isLoading={startMutation.isPending}
              error={errorMessage}
              minLength={10}
              maxLength={2000}
            />

            {/* Clickable Recommended Example Queries */}
            <div className="pt-2 border-t border-slate-100">
              <ExampleQueries
                onSelect={(q) => handleSelectExample(q, false)}
                disabled={startMutation.isPending}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 3. Multi-Agent Architecture Overview */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-slate-50/70 border-slate-200">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center gap-2 text-sg-blue font-semibold text-sm">
              <span className="w-6 h-6 rounded-md bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">
                1
              </span>
              Coordinator Agent
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-slate-600 leading-relaxed">
            Deconstructs complex policy questions into structured research plans, sub-tasks, and target data series.
          </CardContent>
        </Card>

        <Card className="bg-slate-50/70 border-slate-200">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center gap-2 text-emerald-700 font-semibold text-sm">
              <span className="w-6 h-6 rounded-md bg-emerald-100 text-emerald-800 flex items-center justify-center text-xs font-bold">
                2
              </span>
              Extraction Agent
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-slate-600 leading-relaxed">
            Interacts with official SingStat MCP and Data.gov.sg v2; cleans, merges, and validates data structures.
          </CardContent>
        </Card>

        <Card className="bg-slate-50/70 border-slate-200">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center gap-2 text-purple-700 font-semibold text-sm">
              <span className="w-6 h-6 rounded-md bg-purple-100 text-purple-800 flex items-center justify-center text-xs font-bold">
                3
              </span>
              Analytics Agent
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-slate-600 leading-relaxed">
            Executes descriptive/inferential statistical routines and compiles interactive Plotly visualization specifications.
          </CardContent>
        </Card>
      </section>

      {/* 4. Recent Analyses Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-slate-500" />
            <h2 className="text-lg font-bold text-slate-900">Recent Analyses</h2>
          </div>
          <Link
            href="/dashboard/history"
            className="text-xs font-semibold text-sg-blue hover:underline flex items-center gap-1"
          >
            View all history
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {recentItems.length === 0 ? (
          <Card className="p-8 text-center bg-white border-dashed">
            <Clock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
            <h3 className="text-sm font-semibold text-slate-800">No past analyses recorded yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
              Your autonomous research runs will appear here as soon as you submit your first question above.
            </p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {recentItems.map((item) => {
              const status = formatStatus(item.status);
              return (
                <Card
                  key={item.id}
                  className="hover:border-slate-300 transition-shadow hover:shadow-sm"
                >
                  <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${status.bgClass} ${status.textClass} ${status.borderClass}`}
                        >
                          {status.label}
                        </span>
                        <span className="text-xs text-slate-400">
                          {formatDate(item.created_at)}
                        </span>
                        {item.duration_ms && (
                          <span className="text-[11px] text-slate-400">
                            • {(item.duration_ms / 1000).toFixed(1)}s
                          </span>
                        )}
                      </div>
                      <Link
                        href={`/dashboard/analysis/${item.id}`}
                        className="font-medium text-slate-900 hover:text-sg-blue text-sm block line-clamp-2"
                      >
                        {item.query}
                      </Link>
                    </div>

                    <div className="shrink-0">
                      <Link href={`/dashboard/analysis/${item.id}`}>
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          Open Report
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
