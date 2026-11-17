import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExampleQueries, CATEGORIZED_EXAMPLE_QUERIES } from "../query/ExampleQueries";
import { PolicyIndicatorsHub } from "../dashboard/PolicyIndicatorsHub";

describe("ExampleQueries Component", () => {
  it("renders all categorized example policy query cards", () => {
    const handleSelect = jest.fn();
    render(<ExampleQueries onSelect={handleSelect} />);

    expect(screen.getByText(/Recommended Policy Inquiry Benchmarks/i)).toBeInTheDocument();
    expect(screen.getByText(/Population & Demographics/i)).toBeInTheDocument();
    expect(screen.getByText(/Macroeconomic Growth/i)).toBeInTheDocument();
    expect(screen.getByText(/Trade & Investments/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Household Income/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Aging vs Youth/i)).toBeInTheDocument();
  });

  it("calls onSelect with the full query text when clicked", () => {
    const handleSelect = jest.fn();
    render(<ExampleQueries onSelect={handleSelect} />);

    const popQuery = CATEGORIZED_EXAMPLE_QUERIES[0].query;
    const button = screen.getByTitle(`Click to analyze: "${popQuery}"`);
    fireEvent.click(button);

    expect(handleSelect).toHaveBeenCalledWith(popQuery);
  });
});

describe("PolicyIndicatorsHub Component", () => {
  it("renders key national indicator KPI cards", () => {
    const handleSelect = jest.fn();
    render(<PolicyIndicatorsHub onSelectQuery={handleSelect} />);

    expect(screen.getAllByText(/Real GDP Growth/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("+3.6%").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Total Population/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("6.04M").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Fertility Rate \(TFR\)/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("0.97").length).toBeGreaterThan(0);
    expect(screen.getAllByText("S$10,869").length).toBeGreaterThan(0);
  });

  it("switches tabs to Industry and invokes deep dive analysis", () => {
    const handleSelect = jest.fn();
    render(<PolicyIndicatorsHub onSelectQuery={handleSelect} />);

    // Switch to Industries tab
    const indTab = screen.getByRole("button", { name: /Industries/i });
    fireEvent.click(indTab);

    expect(screen.getByText(/Manufacturing \(Electronics, Biomedical, Precision\)/i)).toBeInTheDocument();

    // Click Deep Dive button
    const analyzeBtn = screen.getByRole("button", { name: /Analyze Sectoral GDP & Industry Trends/i });
    fireEvent.click(analyzeBtn);

    expect(handleSelect).toHaveBeenCalledWith(
      expect.stringContaining("Manufacturing, Finance, ICT, and Wholesale Trade")
    );
  });
});
