import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryInput } from "../query/QueryInput";

describe("QueryInput Component", () => {
  it("renders with placeholder and initial value", () => {
    const handleChange = jest.fn();
    const handleSubmit = jest.fn();

    render(
      <QueryInput
        value="Singapore labor statistics"
        onChange={handleChange}
        onSubmit={handleSubmit}
        placeholder="Ask a question..."
      />
    );

    const textarea = screen.getByPlaceholderText("Ask a question...") as HTMLTextAreaElement;
    expect(textarea).toBeInTheDocument();
    expect(textarea.value).toBe("Singapore labor statistics");
  });

  it("calls onChange when typing", () => {
    const handleChange = jest.fn();
    const handleSubmit = jest.fn();

    render(
      <QueryInput
        value=""
        onChange={handleChange}
        onSubmit={handleSubmit}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "New policy query" } });
    expect(handleChange).toHaveBeenCalledWith("New policy query");
  });

  it("shows validation error when query is shorter than minLength", () => {
    const handleChange = jest.fn();
    const handleSubmit = jest.fn();

    render(
      <QueryInput
        value="short"
        onChange={handleChange}
        onSubmit={handleSubmit}
        minLength={10}
      />
    );

    const submitBtn = screen.getByRole("button", { name: /run analysis/i });
    fireEvent.click(submitBtn);

    expect(handleSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/minimum 10 characters/i)).toBeInTheDocument();
  });

  it("submits valid query on button click", () => {
    const handleChange = jest.fn();
    const handleSubmit = jest.fn();

    render(
      <QueryInput
        value="Analyze Singapore GDP growth 2020-2024"
        onChange={handleChange}
        onSubmit={handleSubmit}
        minLength={10}
      />
    );

    const submitBtn = screen.getByRole("button", { name: /run analysis/i });
    fireEvent.click(submitBtn);

    expect(handleSubmit).toHaveBeenCalledWith("Analyze Singapore GDP growth 2020-2024");
  });

  it("disables input and shows loading spinner when isLoading=true", () => {
    const handleChange = jest.fn();
    const handleSubmit = jest.fn();

    render(
      <QueryInput
        value="Valid analysis query"
        onChange={handleChange}
        onSubmit={handleSubmit}
        isLoading={true}
      />
    );

    const submitBtn = screen.getByRole("button", { name: /submitting/i });
    expect(submitBtn).toBeDisabled();
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});
