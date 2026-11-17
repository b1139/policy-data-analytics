"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Download,
  Trash2,
  Clock,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { formatDate, formatUserFriendlyError } from "@/lib/utils";
import { rerunAnalysis } from "@/lib/api";
import { useToast } from "@/components/ui/toaster";
import type { AnalysisListItem, AnalysisStatus } from "@/types";

interface AnalysisCardProps {
  item: AnalysisListItem;
  onDelete: (id: string) => Promise<void> | void;
  onExport: (id: string) => Promise<void> | void;
  isDeleting?: boolean;
  isExporting?: boolean;
}

export function StatusBadge({ status }: { status: AnalysisStatus | string }) {
  const norm = (status || "PENDING").toUpperCase();

  switch (norm) {
    case "DONE":
    case "COMPLETED":
    case "SUCCESS":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle2 className="h-3 w-3 text-emerald-600" />
          <span>Completed</span>
        </span>
      );
    case "RUNNING":
    case "IN_PROGRESS":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
          <span className="animate-pulse">Running</span>
        </span>
      );
    case "FAILED":
    case "ERROR":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
          <XCircle className="h-3 w-3 text-rose-600" />
          <span>Failed</span>
        </span>
      );
    case "PENDING":
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
          <Clock className="h-3 w-3 text-slate-500" />
          <span>Pending</span>
        </span>
      );
  }
}

export function AnalysisCard({
  item,
  onDelete,
  onExport,
  isDeleting = false,
  isExporting = false,
}: AnalysisCardProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [rerunLoading, setRerunLoading] = useState(false);
  const router = useRouter();
  const { toast } = useToast();

  const handleExportClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setExportLoading(true);
      await onExport(item.id);
    } finally {
      setExportLoading(false);
    }
  };

  const handleRerunClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setRerunLoading(true);
      toast({
        title: "Re-running Analysis",
        description: "Re-queuing query pipeline execution...",
      });
      await rerunAnalysis(item.id);
      router.push(`/dashboard/analysis/${item.id}`);
    } catch (err: any) {
      toast({
        title: "Re-run Failed",
        description: err?.message || "Could not re-run analysis.",
        variant: "destructive",
      });
    } finally {
      setRerunLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    try {
      setDeleteLoading(true);
      await onDelete(item.id);
    } finally {
      setDeleteLoading(false);
      setDeleteDialogOpen(false);
    }
  };

  return (
    <Card className="hover:border-slate-300 hover:shadow-md transition-all duration-200 bg-white group">
      <CardContent className="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Left Side: Metadata and Query */}
        <div className="space-y-2 flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <StatusBadge status={item.status} />

            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Clock className="h-3.5 w-3.5" />
              <span>{formatDate(item.created_at)}</span>
            </div>

            {typeof item.duration_ms === "number" && item.duration_ms > 0 && (
              <span className="text-[11px] text-slate-400 font-mono">
                • {(item.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
          </div>

          <Link
            href={`/dashboard/analysis/${item.id}`}
            className="block group-hover:text-sg-blue transition-colors"
          >
            <h3 className="font-semibold text-slate-900 text-sm sm:text-base leading-snug line-clamp-2">
              {item.query}
            </h3>
          </Link>

          {item.error_msg && item.status === "FAILED" && (
            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-2.5 py-1 line-clamp-2">
              <span className="font-medium text-rose-800">Issue: </span>
              {formatUserFriendlyError(item.error_msg)}
            </div>
          )}
        </div>

        {/* Right Side: Quick Action Buttons */}
        <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
          {/* Re-run button for failed queries */}
          {item.status === "FAILED" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRerunClick}
              disabled={rerunLoading}
              className="text-xs gap-1.5 text-amber-700 border-amber-300 bg-amber-50/50 hover:bg-amber-100 hover:text-amber-800 h-8"
              title="Re-run this query"
            >
              {rerunLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5 text-amber-600" />
              )}
              <span>Re-run</span>
            </Button>
          )}

          {/* Export JSON Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportClick}
            disabled={exportLoading || isExporting}
            className="text-xs gap-1.5 text-slate-700 hover:text-slate-900 h-8"
            title="Export analysis as JSON"
          >
            {exportLoading || isExporting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5 text-slate-500" />
            )}
            <span>Export JSON</span>
          </Button>

          {/* Delete with Confirmation Dialog */}
          <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={deleteLoading || isDeleting}
                className="text-xs text-red-600 hover:text-red-700 hover:bg-red-50 h-8 px-2.5"
                title="Delete analysis record"
                aria-label={`Delete analysis ${item.id}`}
              >
                {deleteLoading || isDeleting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <div className="flex items-center gap-2 text-rose-600 mb-1">
                  <AlertTriangle className="h-5 w-5" />
                  <AlertDialogTitle>Delete Analysis Record?</AlertDialogTitle>
                </div>
                <AlertDialogDescription>
                  Are you sure you want to delete this analysis?
                  <span className="block mt-2 p-2.5 bg-slate-50 rounded text-slate-800 font-mono text-xs line-clamp-2 border">
                    &quot;{item.query}&quot;
                  </span>
                  This will permanently remove the research steps, charts, and generated insights.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleteLoading}>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleConfirmDelete}
                  disabled={deleteLoading}
                  className="bg-rose-600 hover:bg-rose-700 text-white gap-1.5"
                >
                  {deleteLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  Delete Record
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {/* Open Detail Page */}
          <Link href={`/dashboard/analysis/${item.id}`}>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs text-sg-blue border-sg-blue/30 hover:bg-sg-blue/5 hover:border-sg-blue h-8"
            >
              <span>Open</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
