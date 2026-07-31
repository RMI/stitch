import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ResourcesTable from "./ResourcesTable";

function renderTable(props) {
  return render(
    <MemoryRouter>
      <ResourcesTable {...props} />
    </MemoryRouter>,
  );
}

const sortConfig = { column: null, direction: "asc" };
const onSort = vi.fn();

const mockResources = [
  {
    id: 1,
    data: {
      name: "Burgan Field",
      country: "NOR",
      state_province: "Kuwait",
      region: "Middle East",
      basin: "Arabian",
      field_status: "Producing",
      primary_hydrocarbon_group: "Oil",
    },
    provenance: { name: "gem" },
  },
];

describe("ResourcesTable", () => {
  it("renders nothing when there are no resources", () => {
    const { container } = renderTable({
      resources: [],
      sortConfig,
      onSort,
      isFetching: false,
    });

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there are no resources, even while fetching", () => {
    const { container } = renderTable({
      resources: [],
      sortConfig,
      onSort,
      isFetching: true,
    });

    expect(container).toBeEmptyDOMElement();
  });

  it("renders real rows when resources are available", () => {
    renderTable({
      resources: mockResources,
      sortConfig,
      onSort,
      isFetching: false,
    });

    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps showing existing rows, dimmed with a spinner, while refetching", () => {
    renderTable({
      resources: mockResources,
      sortConfig,
      onSort,
      isFetching: true,
    });

    // The previous data stays on screen rather than being replaced.
    expect(screen.getByText("Burgan Field")).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(table).toHaveAttribute("aria-busy", "true");
    expect(table.className).toMatch(/opacity-50/);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/updating resources/i)).toBeInTheDocument();
  });

  it("does not dim the table or show a spinner when not fetching", () => {
    renderTable({
      resources: mockResources,
      sortConfig,
      onSort,
      isFetching: false,
    });

    const table = screen.getByRole("table");
    expect(table).not.toHaveAttribute("aria-busy");
    expect(table.className).not.toMatch(/opacity-50/);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
