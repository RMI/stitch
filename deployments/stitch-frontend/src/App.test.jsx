import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithQueryClient } from "./test/utils";
import App from "./App";

describe("App", () => {
  it("renders OGFields heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByText(/^OGFields$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders OGField heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByText(/^OGField ID: \d+$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders both OGFieldsView and OGFieldView components", () => {
    renderWithQueryClient(<App />);

    // Check for OGFieldsView content
    expect(screen.getByText(/^OGFields$/i)).toBeInTheDocument();

    // Check for OGFieldView content
    expect(screen.getByText(/^OGField ID: \d+$/i)).toBeInTheDocument();
  });
});
