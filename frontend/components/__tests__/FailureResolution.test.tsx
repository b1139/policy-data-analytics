import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AnalysisDetailPage from "@/app/dashboard/analysis/[id]/page";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetAnalysis = jest.fn();
const mockRerunAnalysis = jest.fn();
const mockResolveAnalysisData = jest.fn();

jest.mock("@/lib/api", () => ({
  getAnalysis: (...args: any[]) => mockGetAnalysis(...args),
  rerunAnalysis: (...args: any[]) => mockRerunAnalysis(...args),
  resolveAnalysisData: (...args: any[]) => mockResolveAnalysisData(...args),
  exportAnalysis: jest.fn(),
}));

jest.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: () => ({
    steps: [],
    isConnected: true,
    isConnecting: false,
    isDone: false,
    error: null,
    status: "FAILED",
    latestResult: null,
    reconnect: jest.fn(),
  }),
}));

const mockFailedAnalysis = {
  id: "failed-analysis-123",
  query: "What is the 5-year trend in Singapore CPI?",
  status: "FAILED" as const,
  error_msg: "Data extraction failed for 'Consumer Price Index' (id=M212161, source=singstat): Dataset 'M212161' from 'singstat' is empty.",
  result: {
    insights: "",
    charts: [],
    citations: [],
    failed_data: {
      failed_stage: "extraction",
      error: "Data extraction could not retrieve official records for 'Consumer Price Index'.",
      attempted_datasets: [
        {
          dataset_id: "M212161",
          title: "Consumer Price Index (CPI)",
          source: "SingStat Table API",
          topics: ["Inflation", "Consumer Prices"],
        },
      ],
      extraction_errors: ["Dataset 'M212161' from 'singstat' is empty."],
    },
  },
  metadata: {
    sources_used: ["SingStat Table API"],
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("AnalysisDetailPage Failure & AI Resolution", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetAnalysis.mockResolvedValue(mockFailedAnalysis);
    mockRerunAnalysis.mockResolvedValue({
      analysis_id: "failed-analysis-123",
      status: "PENDING",
      ws_url: "ws://localhost:8000/ws/analysis/failed-analysis-123",
    });
    mockResolveAnalysisData.mockResolvedValue({
      ...mockFailedAnalysis,
      status: "DONE",
      error_msg: null,
      result: {
        insights: "Resolved Singapore CPI analysis with steady 2.1% trend.",
        charts: [],
        citations: [],
      },
    });
  });

  it("renders user-friendly failure message without stack traces", async () => {
    renderWithClient(<AnalysisDetailPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/Analysis Execution Encountered an Issue/i)
      ).toBeInTheDocument();
    });

    // Verify friendly error message is shown and no raw traceback exists
    expect(
      screen.getAllByText(/Data extraction could not retrieve official records/i).length
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/Traceback/i)).not.toBeInTheDocument();
  });

  it("displays the target data on which execution failed", async () => {
    renderWithClient(<AnalysisDetailPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/Data on which Query Failed/i)
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Consumer Price Index \(CPI\)/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/ID: M212161/i)).toBeInTheDocument();
    expect(screen.getByText(/Topics: Inflation, Consumer Prices/i)).toBeInTheDocument();
  });

  it("triggers re-run when Re-run Analysis button is clicked", async () => {
    renderWithClient(<AnalysisDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Re-run Analysis/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Re-run Analysis/i }));

    await waitFor(() => {
      expect(mockRerunAnalysis).toHaveBeenCalledWith("test-id");
    });
  });

  it("triggers AI data resolution when Resolve with AI button is clicked", async () => {
    renderWithClient(<AnalysisDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Resolve with AI/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Resolve with AI/i }));

    await waitFor(() => {
      expect(mockResolveAnalysisData).toHaveBeenCalledWith("test-id");
    });
  });
});
