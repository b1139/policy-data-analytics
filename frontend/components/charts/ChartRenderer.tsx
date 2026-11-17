"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import {
  BarChart3,
  Download,
  Table as TableIcon,
  RefreshCw,
  AlertCircle,
  Maximize2,
  TrendingUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChartSpec } from "@/types";
import { NoData } from "@/components/ui/no-data";

declare global {
  interface Window {
    Plotly?: {
      newPlot: (
        root: HTMLElement,
        data: any[],
        layout?: Record<string, any>,
        config?: Record<string, any>
      ) => Promise<any>;
      react: (
        root: HTMLElement,
        data: any[],
        layout?: Record<string, any>,
        config?: Record<string, any>
      ) => Promise<any>;
      purge: (root: HTMLElement) => void;
      downloadImage: (
        root: HTMLElement,
        opts: {
          format: "png" | "jpeg" | "webp" | "svg";
          width?: number;
          height?: number;
          filename?: string;
        }
      ) => Promise<string>;
      Plots: {
        resize: (root: HTMLElement) => void;
      };
    };
  }
}

interface ChartRendererProps {
  charts?: ChartSpec[] | ChartSpec | null;
  loading?: boolean;
  noData?: boolean;
}

function isRenderableChart(c: any): boolean {
  return Boolean(c) && c.type !== "empty_chart" && !c.error && Array.isArray(c.data) && c.data.length > 0;
}

export function ChartRenderer({ charts, loading = false, noData = false }: ChartRendererProps) {
  const chartList: ChartSpec[] = useMemo(() => {
    if (noData || !charts) return [];
    const list = Array.isArray(charts) ? charts : [charts];
    return list.filter(isRenderableChart);
  }, [charts, noData]);

  const [activeChartIndex, setActiveChartIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"chart" | "table">("chart");
  const [plotlyLoaded, setPlotlyLoaded] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);

  const activeChart: ChartSpec | undefined = chartList[activeChartIndex];

  // 1. Client-side dynamically load Plotly.js from CDN without SSR issues
  useEffect(() => {
    let isMounted = true;

    if (typeof window === "undefined") return;

    if (window.Plotly) {
      setPlotlyLoaded(true);
      return;
    }

    const scriptId = "plotly-cdn-script";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;

    if (!script) {
      script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://cdn.plot.ly/plotly-2.32.0.min.js";
      script.async = true;
      script.onload = () => {
        if (isMounted) setPlotlyLoaded(true);
      };
      script.onerror = () => {
        if (isMounted) {
          setRenderError("Failed to load Plotly CDN library. Displaying data table fallback.");
        }
      };
      document.head.appendChild(script);
    } else {
      if (window.Plotly) {
        setPlotlyLoaded(true);
      } else {
        script.addEventListener("load", () => {
          if (isMounted) setPlotlyLoaded(true);
        });
      }
    }

    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Render Plotly figure whenever activeChart, plotlyLoaded, or viewMode changes
  useEffect(() => {
    if (!plotlyLoaded || viewMode !== "chart" || !containerRef.current || !activeChart) {
      return;
    }

    const targetDiv = containerRef.current;
    setRenderError(null);

    try {
      if (!window.Plotly) {
        throw new Error("Plotly runtime not loaded");
      }

      // Check if chart has data traces
      const rawData = activeChart.data || [];
      if (!Array.isArray(rawData) || rawData.length === 0) {
        setRenderError("No visual data series found in chart specification.");
        return;
      }

      // Deep copy layout and configure responsive defaults
      const layout = {
        autosize: true,
        template: "plotly_white",
        font: { family: "system-ui, -apple-system, sans-serif" },
        margin: { l: 50, r: 30, t: 50, b: 50 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        hovermode: "closest",
        legend: { orientation: "h", y: -0.2, x: 0 },
        ...(activeChart.layout || {}),
      };

      const config = {
        responsive: true,
        displayModeBar: false,
        displaylogo: false,
        ...(activeChart.config || {}),
      };

      // Plot
      window.Plotly.newPlot(targetDiv, rawData, layout, config);

      // Handle window resize
      const handleResize = () => {
        if (targetDiv && window.Plotly?.Plots?.resize) {
          window.Plotly.Plots.resize(targetDiv);
        }
      };
      window.addEventListener("resize", handleResize);

      return () => {
        window.removeEventListener("resize", handleResize);
        if (targetDiv && window.Plotly?.purge) {
          window.Plotly.purge(targetDiv);
        }
      };
    } catch (err: any) {
      console.warn("Plotly render warning:", err);
      setRenderError(err?.message || "Error rendering interactive chart. Switched to data view.");
    }
  }, [activeChart, plotlyLoaded, viewMode]);

  // Handle PNG export
  const handleDownloadPNG = async () => {
    if (!containerRef.current || !window.Plotly?.downloadImage || !activeChart) return;
    setIsExporting(true);
    try {
      const title = (activeChart.title || "policy_chart")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_");
      await window.Plotly.downloadImage(containerRef.current, {
        format: "png",
        width: 1000,
        height: 550,
        filename: `${title}_export`,
      });
    } catch (err) {
      console.error("Export PNG failed:", err);
    } finally {
      setIsExporting(false);
    }
  };

  // Extract tabular data from Plotly traces for Fallback & Table View
  const tabularData = useMemo(() => {
    if (!activeChart || !Array.isArray(activeChart.data)) return [];
    const rows: Record<string, any>[] = [];

    const firstTrace = activeChart.data[0] || {};
    const xVals: any[] = Array.isArray(firstTrace.x) ? firstTrace.x : [];

    for (let i = 0; i < xVals.length; i++) {
      const row: Record<string, any> = {
        Period: xVals[i],
      };
      for (const trace of activeChart.data) {
        const traceName = String(trace.name || trace.legendgroup || `Series ${rows.length + 1}`);
        const yVals: any[] = Array.isArray(trace.y) ? trace.y : [];
        row[traceName] = yVals[i] !== undefined ? yVals[i] : null;
      }
      rows.push(row);
    }
    return rows;
  }, [activeChart]);

  // Loading skeleton
  if (loading) {
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b flex flex-row items-center justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
          <Skeleton className="h-8 w-24" />
        </CardHeader>
        <CardContent className="p-6">
          <Skeleton className="h-[360px] w-full rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  // Empty state
  if (chartList.length === 0) {
    const waiting = !noData && !charts;
    return (
      <Card className="border-slate-200 shadow-sm bg-white">
        <CardHeader className="p-5 pb-3 border-b">
          <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-sg-blue" />
            Statistical Visualizations
          </CardTitle>
          <CardDescription className="text-xs">
            {waiting
              ? "Interactive charts will populate when analytics modeling concludes"
              : "No chart could be drawn for this query"}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-12">
          {waiting ? (
            <p className="text-xs text-center text-muted-foreground">Awaiting analytics results...</p>
          ) : (
            <NoData />
          )}
        </CardContent>
      </Card>
    );
  }

  const tableHeaders = tabularData.length > 0 ? Object.keys(tabularData[0]) : [];

  return (
    <Card className="border-slate-200 shadow-sm bg-white overflow-hidden">
      {/* Header with Title, Chart Tabs, and Action Controls */}
      <CardHeader className="p-5 pb-3 border-b space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-blue-600" />
              {activeChart?.title || "Policy Data Visualization"}
            </CardTitle>
            <CardDescription className="text-xs">
              {activeChart?.description || "Interactive time series and comparative policy breakdown"}
            </CardDescription>
          </div>

          {/* Action buttons: View Switcher & PNG Download */}
          <div className="flex items-center gap-1.5 shrink-0">
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100/80 p-0.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewMode("chart")}
                className={`h-7 px-2.5 text-xs font-medium rounded ${
                  viewMode === "chart"
                    ? "bg-white text-slate-900 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Chart
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewMode("table")}
                className={`h-7 px-2.5 text-xs font-medium rounded ${
                  viewMode === "table"
                    ? "bg-white text-slate-900 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <TableIcon className="h-3 w-3 mr-1" />
                Data
              </Button>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadPNG}
              disabled={isExporting || viewMode !== "chart"}
              className="h-8 gap-1.5 text-xs px-2.5"
              title="Download high-resolution chart image"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">PNG</span>
            </Button>
          </div>
        </div>

        {/* Tab pills if multiple charts are present */}
        {chartList.length > 1 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-1 pt-1 border-t border-slate-100">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider shrink-0">
              Charts:
            </span>
            {chartList.map((c, i) => (
              <button
                key={i}
                onClick={() => {
                  setActiveChartIndex(i);
                  setViewMode("chart");
                }}
                className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 ${
                  activeChartIndex === i
                    ? "bg-blue-600 text-white shadow-xs"
                    : "bg-slate-100 hover:bg-slate-200 text-slate-700"
                }`}
              >
                {c.title ? (c.title.length > 25 ? `${c.title.slice(0, 25)}...` : c.title) : `Figure ${i + 1}`}
              </button>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="p-4 sm:p-6">
        {/* Render Error Alert with Fallback toggle */}
        {renderError && (
          <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
              <span>{renderError}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setViewMode("table")}
              className="text-xs text-amber-800 underline hover:bg-transparent h-auto p-0"
            >
              Show Data Table
            </Button>
          </div>
        )}

        {/* Chart View */}
        {viewMode === "chart" && (
          <div className="relative min-h-[380px] w-full flex items-center justify-center">
            {!plotlyLoaded && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/80 z-10 space-y-2">
                <RefreshCw className="h-5 w-5 animate-spin text-blue-600" />
                <span className="text-xs text-muted-foreground font-medium">
                  Loading Plotly visualization engine...
                </span>
              </div>
            )}
            <div
              ref={containerRef}
              className="w-full h-[380px]"
              style={{ minHeight: "380px" }}
            />
          </div>
        )}

        {/* Data Table View (Fallback & Tabular Inspection) */}
        {viewMode === "table" && (
          <div className="w-full space-y-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground pb-1">
              <span>Underlying observations ({tabularData.length} records)</span>
              <Badge variant="outline" className="text-[10px]">
                Tabular Projection
              </Badge>
            </div>
            {tabularData.length > 0 ? (
              <div className="overflow-x-auto border border-slate-200 rounded-lg max-h-[380px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 sticky top-0">
                    <tr>
                      {tableHeaders.map((header) => (
                        <th key={header} className="p-2.5 px-3">
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-800 font-mono">
                    {tabularData.map((row, rIdx) => (
                      <tr key={rIdx} className="hover:bg-slate-50/80 transition-colors">
                        {tableHeaders.map((header) => {
                          const val = row[header];
                          const formatted =
                            typeof val === "number"
                              ? val.toLocaleString(undefined, {
                                  maximumFractionDigits: 2,
                                })
                              : String(val ?? "—");
                          return (
                            <td key={header} className="p-2.5 px-3 whitespace-nowrap">
                              {formatted}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                No tabular series records found in chart specification.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
