import axios, { AxiosInstance } from "axios";
import type { Analysis, AnalysisListItem } from "@/types";

const getBaseURL = (): string => {
  // If NEXT_PUBLIC_API_URL is set, use it; otherwise default to Next.js API rewrite proxy
  const publicApiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (publicApiUrl) {
    // Avoid trailing slash issue
    return publicApiUrl.replace(/\/$/, "") + "/api/v1";
  }
  return "/api/v1";
};

export const apiClient: AxiosInstance = axios.create({
  baseURL: getBaseURL(),
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 60000,
});

export interface StartAnalysisResponse {
  analysis_id: string;
  ws_url?: string;
  query?: string;
  status?: string;
}

export interface ListAnalysesResponse {
  items: AnalysisListItem[];
  total: number;
}

/**
 * Submits a natural-language policy query to trigger multi-agent analysis.
 */
export async function startAnalysis(query: string): Promise<StartAnalysisResponse> {
  const response = await apiClient.post("/analysis/start", { query });
  const data = response.data;
  return {
    analysis_id: data.analysis_id || data.id,
    ws_url: data.ws_url,
    query: data.query,
    status: data.status,
  };
}

/**
 * Retrieves the full analysis details, including agent state, charts, and insights.
 */
export async function getAnalysis(id: string): Promise<Analysis> {
  const response = await apiClient.get<Analysis>(`/analysis/${id}`);
  return response.data;
}

/**
 * Lists past analyses with pagination.
 */
export async function listAnalyses(
  skip: number = 0,
  limit: number = 20
): Promise<ListAnalysesResponse> {
  const response = await apiClient.get<
    | { items: AnalysisListItem[]; total: number }
    | AnalysisListItem[]
  >("/analysis/", {
    params: { skip, limit },
  });

  const data = response.data;
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
    };
  }

  return {
    items: data.items || [],
    total: typeof data.total === "number" ? data.total : (data.items?.length || 0),
  };
}

/**
 * Downloads the exported analysis report as a Blob (JSON/PDF).
 */
export async function exportAnalysis(id: string): Promise<Blob> {
  const response = await apiClient.get(`/analysis/${id}/export`, {
    responseType: "blob",
  });
  return response.data;
}

/**
 * Deletes a past analysis record.
 */
export async function deleteAnalysis(id: string): Promise<void> {
  await apiClient.delete(`/analysis/${id}`);
}

/**
 * Re-runs a previously failed or completed analysis pipeline.
 */
export async function rerunAnalysis(id: string): Promise<StartAnalysisResponse> {
  const response = await apiClient.post(`/analysis/${id}/rerun`);
  const data = response.data;
  return {
    analysis_id: data.analysis_id || data.id,
    ws_url: data.ws_url,
    status: data.status,
  };
}

/**
 * Uses LLM to diagnose data retrieval failure, discover alternative tables, and resolve.
 */
export async function resolveAnalysisData(id: string): Promise<Analysis> {
  const response = await apiClient.post<Analysis>(`/analysis/${id}/resolve-data`);
  return response.data;
}
