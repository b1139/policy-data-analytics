import { downloadAnalysisExport } from "@/hooks/useAnalysis";
import { formatStatus, formatDate } from "@/lib/utils";

describe("History Export and Utility logic", () => {
  it("should have downloadAnalysisExport defined as function", () => {
    expect(typeof downloadAnalysisExport).toBe("function");
  });

  it("should correctly format various analysis statuses", () => {
    const doneStatus = formatStatus("DONE");
    expect(doneStatus.label).toBe("Completed");
    expect(doneStatus.color).toBe("#16A34A");

    const runningStatus = formatStatus("RUNNING");
    expect(runningStatus.label).toBe("Running");
    expect(runningStatus.color).toBe("#F4A201");

    const failedStatus = formatStatus("FAILED");
    expect(failedStatus.label).toBe("Failed");
    expect(failedStatus.color).toBe("#DC2626");

    const pendingStatus = formatStatus("PENDING");
    expect(pendingStatus.label).toBe("Pending");
  });

  it("should format timestamps gracefully", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    const formatted = formatDate("2026-03-01T12:00:00Z");
    expect(typeof formatted).toBe("string");
    expect(formatted.length).toBeGreaterThan(0);
  });
});
