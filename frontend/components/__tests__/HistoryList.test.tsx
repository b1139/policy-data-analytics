/* eslint-disable react/display-name */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { HistoryList } from "../history/HistoryList";
import type { AnalysisListItem } from "@/types";

const mockUseAnalyses = jest.fn();
const mockUseDeleteAnalysis = jest.fn();
const mockDownloadAnalysisExport = jest.fn();

jest.mock("@/hooks/useAnalysis", () => ({
  useAnalyses: (...args: any[]) => mockUseAnalyses(...args),
  useDeleteAnalysis: (...args: any[]) => mockUseDeleteAnalysis(...args),
  downloadAnalysisExport: (...args: any[]) => mockDownloadAnalysisExport(...args),
}));

// Mock next/link to render simple anchor
jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => {
    return <a href={href}>{children}</a>;
  };
  MockLink.displayName = "MockNextLink";
  return MockLink;
});

describe("HistoryList Component", () => {
  const mockMutateAsync = jest.fn();
  const mockRefetch = jest.fn();

  const sampleItems: AnalysisListItem[] = [
    {
      id: "analysis-001",
      query: "Singapore GDP trend 2020-2024",
      status: "DONE",
      created_at: "2026-11-16T08:00:00Z",
      updated_at: "2026-11-16T08:00:10Z",
      duration_ms: 2500,
    },
    {
      id: "analysis-002",
      query: "Tech sector employment changes",
      status: "RUNNING",
      created_at: "2026-11-16T08:05:00Z",
      updated_at: "2026-11-16T08:05:02Z",
      duration_ms: null,
    },
    {
      id: "analysis-003",
      query: "Housing price indices inflation",
      status: "FAILED",
      created_at: "2026-11-16T08:10:00Z",
      updated_at: "2026-11-16T08:10:05Z",
      duration_ms: 1200,
      error_msg: "API rate limit exceeded",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseDeleteAnalysis.mockReturnValue({
      mutateAsync: mockMutateAsync.mockResolvedValue(undefined),
      isPending: false,
    });
    mockDownloadAnalysisExport.mockResolvedValue(undefined);
  });

  it("renders empty state when there are no analyses", () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: [], total: 0, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    expect(screen.getByText("No analyses yet")).toBeInTheDocument();
    expect(screen.getByText(/You have not run any policy research queries yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run First Query/i })).toBeInTheDocument();
  });

  it("renders loading skeletons when loading initial items", () => {
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      error: null,
      refetch: mockRefetch,
    });

    const { container } = render(<HistoryList />);
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders analysis cards when items exist", () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    expect(screen.getByText("Singapore GDP trend 2020-2024")).toBeInTheDocument();
    expect(screen.getByText("Tech sector employment changes")).toBeInTheDocument();
    expect(screen.getByText("Housing price indices inflation")).toBeInTheDocument();

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();

    expect(screen.getByText("Showing 3 of 3 records")).toBeInTheDocument();
  });

  it("filters items by search query", () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    const searchInput = screen.getByPlaceholderText(/Search by policy question/i);
    fireEvent.change(searchInput, { target: { value: "GDP" } });

    expect(screen.getByText("Singapore GDP trend 2020-2024")).toBeInTheDocument();
    expect(screen.queryByText("Tech sector employment changes")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 3 records")).toBeInTheDocument();
  });

  it("shows no matching analyses message when search filter yields 0 items", () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    const searchInput = screen.getByPlaceholderText(/Search by policy question/i);
    fireEvent.change(searchInput, { target: { value: "NonExistentKeyword" } });

    expect(screen.getByText("No matching analyses found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reset Filters/i })).toBeInTheDocument();

    // Clicking Reset Filters clears filter
    fireEvent.click(screen.getByRole("button", { name: /Reset Filters/i }));
    expect(screen.getByText("Singapore GDP trend 2020-2024")).toBeInTheDocument();
  });

  it("filters items by status button (DONE)", () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    const doneButton = screen.getByRole("button", { name: "DONE" });
    fireEvent.click(doneButton);

    expect(screen.getByText("Singapore GDP trend 2020-2024")).toBeInTheDocument();
    expect(screen.queryByText("Tech sector employment changes")).not.toBeInTheDocument();
    expect(screen.queryByText("Housing price indices inflation")).not.toBeInTheDocument();
  });

  it("opens delete confirmation dialog and triggers delete mutation", async () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    const deleteBtn = screen.getByLabelText("Delete analysis analysis-001");
    fireEvent.click(deleteBtn);

    expect(screen.getByText("Delete Analysis Record?")).toBeInTheDocument();
    expect(
      screen.getByText(/Are you sure you want to delete this analysis\?/i)
    ).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: /Delete Record/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith("analysis-001");
    });
  });

  it("triggers export handler when Export JSON button is clicked", async () => {
    mockUseAnalyses.mockReturnValue({
      data: { items: sampleItems, total: 3, skip: 0, limit: 20 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    const exportButtons = screen.getAllByRole("button", { name: /Export JSON/i });
    fireEvent.click(exportButtons[0]);

    await waitFor(() => {
      expect(mockDownloadAnalysisExport).toHaveBeenCalledWith("analysis-001");
    });
  });

  it("renders error card when API returns error", () => {
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: new Error("Network error connecting to backend"),
      refetch: mockRefetch,
    });

    render(<HistoryList />);

    expect(screen.getByText("Failed to load analysis history")).toBeInTheDocument();
    expect(screen.getByText(/Network error connecting to backend/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try Again/i })).toBeInTheDocument();
  });
});
