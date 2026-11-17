"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAnalyses,
  getAnalysis,
  deleteAnalysis as deleteAnalysisApi,
  exportAnalysis as exportAnalysisApi,
  ListAnalysesResponse,
} from "@/lib/api";
import type { Analysis, AnalysisListItem } from "@/types";

export interface UseAnalysesOptions {
  skip?: number;
  limit?: number;
  enabled?: boolean;
}

/**
 * Direct client-side trigger to download an analysis export JSON blob.
 */
export async function downloadAnalysisExport(id: string): Promise<void> {
  const blob = await exportAnalysisApi(id);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `analysis_${id}.json`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

/**
 * Hook to query paginated list of analyses with caching and refetching.
 */
export function useAnalyses({
  skip = 0,
  limit = 20,
  enabled = true,
}: UseAnalysesOptions = {}) {
  return useQuery<ListAnalysesResponse, Error>({
    queryKey: ["analyses", skip, limit],
    queryFn: () => listAnalyses(skip, limit),
    enabled,
    staleTime: 10 * 1000,
  });
}

/**
 * Hook to delete an analysis with optimistic UI update and cache invalidation.
 */
export function useDeleteAnalysis() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string, { previousQueries?: [unknown, unknown][] }>({
    mutationFn: (id: string) => deleteAnalysisApi(id),
    onMutate: async (idToDelete: string) => {
      // Cancel any outgoing queries so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ["analyses"] });

      // Snapshot previous data for rollback
      const previousQueries = queryClient.getQueriesData<ListAnalysesResponse>({
        queryKey: ["analyses"],
      });

      // Optimistically update all cached list results
      queryClient.setQueriesData<ListAnalysesResponse>(
        { queryKey: ["analyses"] },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.filter((item) => item.id !== idToDelete),
            total: Math.max(0, (old.total ?? old.items.length) - 1),
          };
        }
      );

      return { previousQueries };
    },
    onError: (_err, _id, context) => {
      // Revert cache to snapshot on error
      if (context?.previousQueries) {
        context.previousQueries.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey as any, data);
        });
      }
    },
    onSettled: () => {
      // Always refetch to sync with server state
      queryClient.invalidateQueries({ queryKey: ["analyses"] });
    },
  });
}

/**
 * Hook for downloading / exporting an analysis JSON blob.
 */
export function useExportAnalysis() {
  return useMutation<void, Error, string>({
    mutationFn: (id: string) => downloadAnalysisExport(id),
  });
}

/**
 * Primary useAnalysis hook providing both single analysis fetching
 * and CRUD operations (get, delete, export).
 */
export function useAnalysis(id?: string) {
  const queryClient = useQueryClient();
  const deleteMutation = useDeleteAnalysis();
  const exportMutation = useExportAnalysis();

  const singleQuery = useQuery<Analysis, Error>({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id!),
    enabled: Boolean(id),
    staleTime: 15 * 1000,
  });

  return {
    // Single analysis data & query state
    analysis: singleQuery.data ?? null,
    isLoading: singleQuery.isLoading,
    isError: singleQuery.isError,
    error: singleQuery.error,
    refetch: singleQuery.refetch,

    // Mutation actions
    deleteAnalysis: (targetId: string) => deleteMutation.mutateAsync(targetId),
    isDeleting: deleteMutation.isPending,
    exportAnalysis: (targetId: string) => exportMutation.mutateAsync(targetId),
    isExporting: exportMutation.isPending,

    // Helper to invalidate all analysis queries
    invalidateAnalyses: () => queryClient.invalidateQueries({ queryKey: ["analyses"] }),
  };
}
