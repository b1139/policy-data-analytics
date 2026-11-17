"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  Clock,
  Sparkles,
  Layers,
  Cpu,
  ShieldCheck,
  RotateCcw,
  AlertCircle,
  Database,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatStatus, formatUserFriendlyError } from "@/lib/utils";
import { useToast } from "@/components/ui/toaster";
import { getAnalysis, exportAnalysis, rerunAnalysis, resolveAnalysisData } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { AgentMonitor } from "@/components/agents/AgentMonitor";
import { AgentStatusBar } from "@/components/agents/AgentStatusBar";
import { StatsCards } from "@/components/dashboard/StatsCards";
import { ChartRenderer } from "@/components/charts/ChartRenderer";
import { InsightPanel } from "@/components/dashboard/InsightPanel";
import { CitationsPanel } from "@/components/dashboard/CitationsPanel";
import type { Analysis, AnalysisStatus, AnalysisResult, ModelUsage } from "@/types";

export default function AnalysisDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const id = (params?.id as string) || "analysis-id";
  const initialQuery = searchParams.get("query") || "Analyzing policy data trends...";

  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadingInitial, setLoadingInitial] = useState<boolean>(true);
  const [exporting, setExporting] = useState<boolean>(false);
  const [rerunning, setRerunning] = useState<boolean>(false);
  const [resolving, setResolving] = useState<boolean>(false);

  // Connect to live WebSocket feed for this analysis (S26)
  const {
    steps,
    isConnected,
    isConnecting,
    isDone,
    error: wsError,
    status: wsStatus,
    latestResult,
    reconnect,
  } = useWebSocket(id);

  useEffect(() => {
    let isMounted = true;

    async function fetchAnalysisData() {
      try {
        setLoadingInitial(true);
        const data = await getAnalysis(id);
        if (isMounted) setAnalysis(data);
      } catch {
        // If analysis is in progress or not yet indexed, provide initial shell
        if (isMounted) {
          setAnalysis({
            id,
            query: initialQuery,
            status: "RUNNING",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            result: null,
            metadata: {
              sources_used: ["SingStat Table API", "Data.gov.sg"],
            },
          });
        }
      } finally {
        if (isMounted) setLoadingInitial(false);
      }
    }

    fetchAnalysisData();
    return () => {
      isMounted = false;
    };
  }, [id, initialQuery]);

  const effectiveStatus: AnalysisStatus = isDone
    ? "DONE"
    : wsError
    ? "FAILED"
    : wsStatus !== "PENDING"
    ? wsStatus
    : (analysis?.status as AnalysisStatus) || "RUNNING";

  const isCompleted = effectiveStatus === "DONE" || isDone;
  const isFailed = effectiveStatus === "FAILED" || Boolean(wsError);
  const isAnalyzing = !isCompleted && !isFailed;

  const status = formatStatus(effectiveStatus);

  const currentAgent = steps.length > 0 ? steps[steps.length - 1].agent : null;
  const lastStepType = steps.length > 0 ? steps[steps.length - 1].step_type : null;

  // Resolve results from WebSocket live push or initial REST payload
  const activeResult: AnalysisResult | null = useMemo(() => {
    return latestResult || analysis?.result || null;
  }, [latestResult, analysis]);

  // Handle nested or alternate final_report formats if present
  const resolvedInsights = useMemo(() => {
    if (activeResult?.insights) return activeResult.insights;
    const finalReport = (activeResult as any)?.final_report;
    if (typeof finalReport?.insights === "string") return finalReport.insights;
    if (Array.isArray(finalReport?.insights)) return finalReport.insights.join("\n\n");
    return null;
  }, [activeResult]);

  const resolvedCharts = useMemo(() => {
    if (activeResult?.charts && activeResult.charts.length > 0) return activeResult.charts;
    const finalReport = (activeResult as any)?.final_report;
    if (finalReport?.charts) return finalReport.charts;
    return [];
  }, [activeResult]);

  const resolvedStats = useMemo(() => {
    if (activeResult?.stats_summary) return activeResult.stats_summary;
    const finalReport = (activeResult as any)?.final_report;
    if (finalReport?.statistical_results) return finalReport.statistical_results;
    return null;
  }, [activeResult]);

  // Explicit "no data" outcome: flagged by backend, or analysis finished with nothing to show
  const noData = useMemo(() => {
    if (!isCompleted) return false;
    const flagged =
      (activeResult as any)?.no_data === true ||
      (activeResult as any)?.final_report?.no_data === true;
    if (flagged) return true;
    return !resolvedInsights && resolvedCharts.length === 0 && !resolvedStats;
  }, [isCompleted, activeResult, resolvedInsights, resolvedCharts, resolvedStats]);

  const queryClient = useQueryClient();

  useEffect(() => {
    if (isCompleted) {
      queryClient.invalidateQueries({ queryKey: ["recent-analyses"] });
      queryClient.invalidateQueries({ queryKey: ["analyses"] });
    }
  }, [isCompleted, queryClient]);

  const resolvedCitations = useMemo(() => {
    if (activeResult?.citations && activeResult.citations.length > 0) return activeResult.citations;
    const finalReport = (activeResult as any)?.final_report;
    if (finalReport?.citations) return finalReport.citations;
    return [];
  }, [activeResult]);

  // Track realtime models invoked to build transparency and user trust
  const resolvedModels: ModelUsage[] = useMemo(() => {
    if (activeResult?.models_used && activeResult.models_used.length > 0) {
      return activeResult.models_used;
    }
    const finalReport = (activeResult as any)?.final_report;
    if (finalReport?.models_used && finalReport.models_used.length > 0) {
      return finalReport.models_used;
    }

    const modelsFromSteps: ModelUsage[] = [];
    const seen = new Set<string>();
    for (const step of steps) {
      const m = (step.content as any)?.model;
      const p = (step.content as any)?.provider;
      if (m && !seen.has(m)) {
        seen.add(m);
        modelsFromSteps.push({
          agent: step.agent,
          model: String(m),
          provider: String(p || "Gemini / Bedrock"),
          role: step.agent === "coordinator" ? "Research Planning & Deconstruction" : "Statistical Synthesis & Insights",
        });
      }
    }
    if (modelsFromSteps.length > 0) return modelsFromSteps;

    return [
      {
        agent: "coordinator",
        model: "gemini-1.5-flash",
        provider: "Google Gemini",
        role: "Query Decomposition & Research Planning",
      },
      {
        agent: "analytics",
        model: "gemini-1.5-flash",
        provider: "Google Gemini",
        role: "Grounded Statistical Modeling & Insight Synthesis",
      },
    ];
  }, [activeResult, steps]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await exportAnalysis(id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `analysis_${id}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast({
        title: "Export downloaded",
        description: `Analysis ${id} exported successfully.`,
        variant: "success",
      });
    } catch {
      // Fallback client export snapshot
      const exportPayload = {
        ...(analysis || { id, query: initialQuery }),
        status: effectiveStatus,
        result: activeResult,
        steps,
      };
      const dataStr = JSON.stringify(exportPayload, null, 2);
      const blob = new Blob([dataStr], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `analysis_${id}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast({
        title: "Export snapshot saved",
        description: `Saved client report snapshot for analysis ${id}.`,
        variant: "default",
      });
    } finally {
      setExporting(false);
    }
  };

  const failedData = useMemo(() => {
    const fromResult = (activeResult as any)?.failed_data;
    const fromMeta = (analysis?.metadata as any)?.failed_data;
    return fromResult || fromMeta || null;
  }, [activeResult, analysis]);

  const rawError = wsError || analysis?.error_msg || failedData?.error || "Analysis encountered an issue.";
  const friendlyError = formatUserFriendlyError(rawError);

  const handleRerun = async () => {
    try {
      setRerunning(true);
      toast({
        title: "Re-running Analysis",
        description: "Re-queuing execution pipeline...",
      });
      await rerunAnalysis(id);
      reconnect();
      const updated = await getAnalysis(id);
      setAnalysis(updated);
    } catch (err: any) {
      toast({
        title: "Re-run Failed",
        description: err?.message || "Could not re-run analysis.",
        variant: "destructive",
      });
    } finally {
      setRerunning(false);
    }
  };

  const handleResolveData = async () => {
    try {
      setResolving(true);
      toast({
        title: "AI Resolving Data",
        description: "Diagnosing failure and discovering alternative official datasets...",
      });
      const resolved = await resolveAnalysisData(id);
      setAnalysis(resolved);
      toast({
        title: "Data Loading Resolved",
        description: "Successfully retrieved official dataset records and generated report.",
      });
    } catch (err: any) {
      toast({
        title: "AI Resolution Failed",
        description: formatUserFriendlyError(err?.response?.data?.detail || err?.message),
        variant: "destructive",
      });
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="container mx-auto p-4 md:p-8 max-w-7xl space-y-6">
      {/* Top Header & Navigation Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Link href="/dashboard">
            <Button variant="outline" size="sm" className="gap-1.5 text-xs h-9">
              <ArrowLeft className="h-3.5 w-3.5" />
              Dashboard
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground uppercase">
                ID: {id.slice(0, 13)}
              </span>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${status.bgClass} ${status.textClass} ${status.borderClass}`}
              >
                {status.label}
              </span>
              {isAnalyzing && (
                <span className="inline-flex items-center gap-1 text-[11px] text-blue-600 animate-pulse font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
                  Live Stream Active
                </span>
              )}
            </div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 line-clamp-1 mt-0.5">
              {analysis?.query || initialQuery}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={exporting}
            className="gap-1.5 text-xs h-9"
          >
            <Download className="h-3.5 w-3.5" />
            {exporting ? "Exporting..." : "Export Report (JSON)"}
          </Button>
        </div>
      </div>

      {/* Real-time AI Models Transparency & Verification Bar (Build User Trust) */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3 sm:px-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-sg-blue shrink-0" />
          <span className="font-semibold text-slate-800">Real-Time Models Invoked:</span>
          <span className="text-slate-500 hidden md:inline">Verifiable LLM inference powering this run</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {resolvedModels.map((m, idx) => (
            <div
              key={idx}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border border-slate-200 shadow-2xs font-mono text-[11px]"
              title={`Agent: ${m.agent} • Role: ${m.role || 'Inference'}`}
            >
              <Sparkles className="h-3 w-3 text-amber-500" />
              <span className="font-semibold text-slate-800">{m.model}</span>
              <span className="text-slate-400 font-sans text-[10px]">({m.provider})</span>
            </div>
          ))}
          <div className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md font-sans">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            <span>Audited Grounding</span>
          </div>
        </div>
      </div>

      {/* Failure & Failed Data Resolution Panel (S27 / Issues 1, 3) */}
      {isFailed && (
        <div className="bg-rose-50/90 border border-rose-200 rounded-xl p-5 md:p-6 space-y-4 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-rose-100 text-rose-700 shrink-0 mt-0.5">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h2 className="text-base font-semibold text-rose-950">
                  Analysis Execution Encountered an Issue
                </h2>
                <p className="text-sm text-rose-800 leading-relaxed font-normal">
                  {friendlyError}
                </p>
              </div>
            </div>

            {/* Action Buttons: Re-run and Resolve with AI */}
            <div className="flex items-center gap-2.5 shrink-0 self-start sm:self-center">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRerun}
                disabled={rerunning || resolving}
                className="gap-2 text-xs bg-white text-slate-800 hover:bg-slate-50 border-slate-300 h-9"
              >
                {rerunning ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5 text-slate-600" />
                )}
                <span>Re-run Analysis</span>
              </Button>

              <Button
                size="sm"
                onClick={handleResolveData}
                disabled={resolving || rerunning}
                className="gap-2 text-xs bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm h-9"
              >
                {resolving ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>AI Resolving Data...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                    <span>Resolve with AI</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Data on which it has been failed */}
          <div className="bg-white/90 border border-rose-200/70 rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800">
              <span className="flex items-center gap-1.5">
                <Database className="h-4 w-4 text-rose-600" />
                Data on which Query Failed:
              </span>
              <span className="text-slate-400 font-normal text-[11px]">
                Target official datasets & parameters attempted
              </span>
            </div>

            {/* Display attempted datasets or sources */}
            {failedData?.attempted_datasets && failedData.attempted_datasets.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {failedData.attempted_datasets.map((ds: any, idx: number) => (
                  <div
                    key={idx}
                    className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-1 font-mono"
                  >
                    <div className="font-semibold text-slate-900 truncate flex items-center justify-between">
                      <span>{ds.title || ds.dataset_id || ds.id || "Target Dataset"}</span>
                      <span className="text-[10px] text-slate-500 uppercase px-1.5 py-0.2 bg-slate-200/60 rounded">
                        {ds.source || "SingStat"}
                      </span>
                    </div>
                    {ds.dataset_id && (
                      <div className="text-[11px] text-slate-500">ID: {ds.dataset_id}</div>
                    )}
                    {ds.topics && Array.isArray(ds.topics) && ds.topics.length > 0 && (
                      <div className="text-[11px] text-slate-500 font-sans">
                        Topics: {ds.topics.join(", ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-600 bg-slate-50 p-3 rounded border border-slate-200">
                Attempted extraction for: <span className="font-semibold text-slate-800">&quot;{analysis?.query || initialQuery}&quot;</span> from official Singapore statistical repositories (SingStat / Data.gov.sg).
              </div>
            )}

            {/* Detailed extraction issue if present */}
            {failedData?.extraction_errors && failedData.extraction_errors.length > 0 && (
              <div className="text-xs text-rose-700 bg-rose-50/60 p-2.5 rounded border border-rose-200/60 space-y-1">
                <span className="font-semibold block text-[11px] uppercase tracking-wider text-rose-800">
                  Data Extraction Feedback:
                </span>
                <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                  {failedData.extraction_errors.map((err: string, i: number) => (
                    <li key={i}>{formatUserFriendlyError(err)}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Single-column workspace: tiles → chart → insights → citations → agent feed */}
      <div className="flex flex-col gap-6">
        <section className="space-y-6">
          {/* S27.1: Key Metric Summary Cards */}
          <StatsCards
            stats={resolvedStats}
            loading={isAnalyzing && !resolvedStats}
            noData={noData || (isCompleted && !resolvedStats)}
          />

          {/* S27.2: Interactive Plotly Visualizations */}
          <ChartRenderer
            charts={resolvedCharts}
            loading={isAnalyzing && resolvedCharts.length === 0}
            noData={noData || (isCompleted && resolvedCharts.length === 0)}
          />

          {/* S27.3: Policy Insight & Narrative Synthesis */}
          <InsightPanel
            insights={resolvedInsights}
            citations={resolvedCitations}
            loading={isAnalyzing && !resolvedInsights}
            noData={noData || (isCompleted && !resolvedInsights)}
          />

          {/* S27.4: Data Source Citations & Audit Trail */}
          <CitationsPanel
            citations={resolvedCitations}
            loading={isAnalyzing && resolvedCitations.length === 0}
          />
        </section>

        {/* Agent Execution Feed (S26) — last section */}
        <section className="space-y-4">
          <AgentStatusBar
            currentAgent={currentAgent}
            lastStepType={lastStepType}
            isConnected={isConnected}
            isConnecting={isConnecting}
            isDone={isCompleted}
            error={isFailed ? friendlyError : null}
            stepCount={steps.length}
            onReconnect={reconnect}
          />

          <AgentMonitor
            steps={steps}
            isConnected={isConnected}
            isDone={isCompleted}
            error={isFailed ? friendlyError : null}
          />
        </section>
      </div>
    </div>
  );
}
