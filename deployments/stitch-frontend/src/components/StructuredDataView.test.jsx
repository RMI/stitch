import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import StructuredDataView from "./StructuredDataView";

describe("StructuredDataView", () => {
  it("renders object rows with primitive columns and nested details", () => {
    render(
      <StructuredDataView
        label="Rows"
        data={[
          { id: "a", name: "Alpha", metrics: { count: 2 } },
          { id: "b", name: "Beta" },
        ]}
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText("ID")).toBeInTheDocument();
    expect(within(table).getByText("Name")).toBeInTheDocument();
    expect(within(table).getByText("Details")).toBeInTheDocument();
    expect(within(table).getByText("Alpha")).toBeInTheDocument();
    expect(within(table).getByText("Metrics: 1 field")).toBeInTheDocument();
  });

  it("falls back to record sections when primitive columns exceed the table cap", () => {
    render(
      <StructuredDataView
        label="Wide rows"
        data={[
          {
            id: "wide-1",
            column_one: "one",
            column_two: "two",
            column_three: "three",
            column_four: "four",
            column_five: "five",
            column_six: "six",
            column_seven: "seven",
            column_eight: "eight",
            column_nine: "nine",
          },
        ]}
      />,
    );

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Record 1", level: 3 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Column Nine")).toBeInTheDocument();
    expect(screen.getByText("nine")).toBeInTheDocument();
  });

  it("uses the requested starting heading level for nested sections", () => {
    render(
      <StructuredDataView
        label="Source data"
        headingLevel={2}
        data={{ source_records: [{ name: "Alpha" }] }}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Source Records", level: 2 }),
    ).toBeInTheDocument();
  });
});
