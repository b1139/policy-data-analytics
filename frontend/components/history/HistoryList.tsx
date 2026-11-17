"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import {
  History,
  Search,
  RefreshCw,
  PlusCircle,
  FileQuestion,
  ChevronDown,
  Loader2,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { useAnalyses, useDeleteAnalysis, downloadAnalysisExport } from "@/hooks/useAnalysis";
import { AnalysisCard } from "@/components/history/AnalysisCard";
import type { AnalysisListItem, AnalysisStatus } from "@/types";

const PAGE_SIZE = 20;

export function HistoryList() {
  const { toast } = useToast();
  const [skip, setSkip] = useState<number>(0);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [allLoadedItems, setAllLoadedItems] = useState<AnalysisListItem[]>([]);

  // TanStack Query for analysis list
  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useAnalyses({ skip, limit: PAGE_SIZE });

  // Delete mutation with optimistic cache update
  const deleteMutation = useDeleteAnalysis();

  // Merge newly fetched items into accumulated list
  React.useEffect(() => {
    if (data?.items) {
      if (skip === 0) {
        setAllLoadedItems(data.items);
      } else {
        setAllLoadedItems((prev) => {
          const existingIds = new Set(prev.map((i) => i.id));
          const newItems = data.items.filter((i) => !existingIds.has(i.id));
          return [...prev, ...newItems];
        });
      }
    }
  }, [data, skip]);

  const total = data?.total ?? allLoadedItems.length;
  const hasMore = allLoadedItems.length < total;

  const handleLoadMore = () => {
    setSkip((prev) => prev + PAGE_SIZE);
  };

  const handleRefresh = async () => {
    setSkip(0);
    await refetch();
    toast({
      title: "History refreshed",
      description: "Analysis records updated.",
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMutation.mutateAsync(id);
      // Also update local accumulated state
      setAllLoadedItems((prev) => prev.filter((item) => item.id !== id));
      toast({
        title: "Analysis deleted",
        description: `Analysis record ${id} removed successfully.`,
        variant: "default",
      });
    } catch (err: any) {
      toast({
        title: "Delete failed",
        description: err?.message || "Could not delete analysis record.",
        variant: "destructive",
      });
    }
  };

  const handleExport = async (id: string) => {
    try {
      await downloadAnalysisExport(id);
      toast({
        title: "Export downloaded",
        description: `Saved analysis_${id}.json to your downloads.`,
        variant: "success",
      });
    } catch (err: any) {
      toast({
        title: "Export failed",
        description: err?.message || "Could not download analysis file.",
        variant: "destructive",
      });
    }
  };

  // Filter items by search query and status
  const filteredItems = useMemo(() => {
    return allLoadedItems.filter((item) => {
      const matchesSearch =
        item.query.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.id.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus =
        statusFilter === "ALL" ||
        item.status.toUpperCase() === statusFilter.toUpperCase();

      return matchesSearch && matchesStatus;
    });
  }, [allLoadedItems, searchTerm, statusFilter]);

  return (
    <div className="space-y-6">
      {/* Search & Status Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search by policy question, keywords, or ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9 bg-white"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm("")}
              className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600 bg-slate-100 rounded px-1.5 py-0.5"
            >
              Clear
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Status Filter Badges/Dropdown */}
          <div className="flex items-center bg-white border rounded-lg p-1 text-xs">
            {(["ALL", "DONE", "RUNNING", "FAILED"] as const).map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  statusFilter === status
                    ? "bg-slate-900 text-white shadow-xs"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                {status === "ALL" ? "All" : status}
              </button>
            ))}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading || isFetching}
            className="gap-1.5 text-xs h-9"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </div>

      {/* Main List Area */}
      {isLoading && allLoadedItems.length === 0 ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((n) => (
            <Card key={n} className="p-5 bg-white">
              <div className="flex justify-between items-center gap-4">
                <div className="space-y-2 flex-1">
                  <div className="flex gap-2">
                    <Skeleton className="h-5 w-20 rounded-full" />
                    <Skeleton className="h-5 w-32" />
                  </div>
                  <Skeleton className="h-5 w-3/4" />
                </div>
                <div className="flex gap-2">
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-16" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : error && allLoadedItems.length === 0 ? (
        <Card className="p-8 text-center bg-white border-dashed">
          <FileQuestion className="h-10 w-10 text-rose-400 mx-auto mb-2" />
          <h3 className="text-sm font-semibold text-slate-800">
            Failed to load analysis history
          </h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
            {error.message || "An unexpected error occurred while fetching analysis records."}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            className="mt-4 gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Try Again
          </Button>
        </Card>
      ) : allLoadedItems.length === 0 ? (
        /* Empty State */
        <Card className="p-12 text-center bg-white border-dashed">
          <div className="h-14 w-14 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4 text-slate-400">
            <History className="h-7 w-7" />
          </div>
          <h3 className="text-base font-semibold text-slate-900">
            No analyses yet
          </h3>
          <p className="text-sm text-slate-500 mt-1.5 max-w-md mx-auto">
            You have not run any policy research queries yet. Ask your first natural language question to coordinate multi-agent data gathering and analytics.
          </p>
          <div className="mt-6">
            <Link href="/dashboard">
              <Button className="bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2">
                <PlusCircle className="h-4 w-4" />
                <span>Run First Query</span>
              </Button>
            </Link>
          </div>
        </Card>
      ) : filteredItems.length === 0 ? (
        /* Search/Filter Empty State */
        <Card className="p-8 text-center bg-white border-dashed">
          <Search className="h-8 w-8 text-slate-300 mx-auto mb-2" />
          <h3 className="text-sm font-semibold text-slate-700">
            No matching analyses found
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            No records matched &quot;{searchTerm}&quot;
            {statusFilter !== "ALL" && ` with status ${statusFilter}`}.
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearchTerm("");
              setStatusFilter("ALL");
            }}
            className="mt-3 text-xs text-sg-blue hover:underline"
          >
            Reset Filters
          </Button>
        </Card>
      ) : (
        /* Populated List */
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span>
              Showing {filteredItems.length} of {total} record{total === 1 ? "" : "s"}
            </span>
            {isFetching && (
              <span className="flex items-center gap-1 text-sg-blue">
                <Loader2 className="h-3 w-3 animate-spin" />
                Updating...
              </span>
            )}
          </div>

          {filteredItems.map((item) => (
            <AnalysisCard
              key={item.id}
              item={item}
              onDelete={handleDelete}
              onExport={handleExport}
              isDeleting={deleteMutation.isPending}
            />
          ))}

          {/* Load More Button */}
          {hasMore && !searchTerm && statusFilter === "ALL" && (
            <div className="pt-4 flex justify-center">
              <Button
                variant="outline"
                onClick={handleLoadMore}
                disabled={isFetching}
                className="gap-2 text-xs"
              >
                {isFetching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
                Load More Analyses ({allLoadedItems.length} of {total})
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
