import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentMonitor } from "../agents/AgentMonitor";
import type { AgentStep } from "@/types";

describe("AgentMonitor Component", () => {
  const mockSteps: AgentStep[] = [
    {
      id: "step-1",
      agent: "coordinator",
      step_type: "THINK",
      content: { reasoning: "Planning research queries for labor dataset" },
      timestamp: "2026-11-16T08:00:00Z",
    },
    {
      id: "step-2",
      agent: "extraction",
      step_type: "ACT",
      content: { tool: "fetch_singstat_data", reasoning: "Querying SingStat Table Builder API" },
      timestamp: "2026-11-16T08:00:02Z",
    },
    {
      id: "step-3",
      agent: "analytics",
      step_type: "OBSERVE",
      content: { observation: "Computing trend line and YoY changes" },
      timestamp: "2026-11-16T08:00:04Z",
    },
  ];

  it("renders empty state when no steps are provided", () => {
    render(<AgentMonitor steps={[]} />);
    expect(screen.getByText(/waiting for agents to start/i)).toBeInTheDocument();
  });

  it("renders agent steps with badges and content", () => {
    render(<AgentMonitor steps={mockSteps} />);

    expect(screen.getByText("Planning research queries for labor dataset")).toBeInTheDocument();
    expect(screen.getByText("Querying SingStat Table Builder API")).toBeInTheDocument();
    expect(screen.getByText("Computing trend line and YoY changes")).toBeInTheDocument();

    expect(screen.getByText("coordinator")).toBeInTheDocument();
    expect(screen.getByText("extraction")).toBeInTheDocument();
    expect(screen.getByText("analytics")).toBeInTheDocument();
  });

  it("renders step count in header badge", () => {
    render(<AgentMonitor steps={mockSteps} />);
    expect(screen.getByText("3 steps")).toBeInTheDocument();
  });

  it("filters steps when filter select changes", () => {
    render(<AgentMonitor steps={mockSteps} />);
    const agentFilter = screen.getByLabelText(/filter steps by agent/i);
    fireEvent.change(agentFilter, { target: { value: "coordinator" } });

    expect(screen.getByText("Planning research queries for labor dataset")).toBeInTheDocument();
    expect(screen.queryByText("Querying SingStat Table Builder API")).not.toBeInTheDocument();
  });
});
