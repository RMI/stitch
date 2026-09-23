import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
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

// Several rows are required to cover row-to-row link bleed (STIT-737); a
// single-row table cannot express that class of bug.
const multipleMockResources = [
  ...mockResources,
  {
    id: 27,
    data: {
      name: "Ghawar Field",
      country: "SAU",
      state_province: "Eastern Province",
      region: "Middle East",
      basin: "Arabian",
      field_status: "Producing",
      primary_hydrocarbon_group: "Oil",
    },
    provenance: { name: "gem" },
  },
  {
    id: 384,
    data: {
      name: "Troll Field",
      country: "NOR",
      state_province: "Rogaland",
      region: "Europe",
      basin: "North Sea",
      field_status: "Producing",
      primary_hydrocarbon_group: "Gas",
    },
    provenance: { name: "gem" },
  },
];

function rowsAndNames(container) {
  return [...container.querySelectorAll("tbody tr")].map((row, index) => [
    row,
    multipleMockResources[index].data.name,
  ]);
}

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

  describe("row links (STIT-737)", () => {
    it("points each row's name link at its own resource", () => {
      renderTable({
        resources: multipleMockResources,
        sortConfig,
        onSort,
        isFetching: false,
      });

      for (const resource of multipleMockResources) {
        expect(
          screen.getByRole("link", { name: resource.data.name }),
        ).toHaveAttribute("href", `/oil-gas-fields/${resource.id}`);
      }
    });

    // Regression guard for STIT-737. The row-wide click target used to be a
    // single overlay anchored to `position: relative` on the <tr>, which CSS
    // 2.1 leaves undefined for table rows and WebKit ignores. Every row's
    // overlay then resolved against the scroll container and covered the whole
    // table, so in Safari all rows led to the last resource. Anchoring each
    // overlay to its own cell keeps the containing block inside the row.
    it("keeps every row's click target inside that row", () => {
      const { container } = renderTable({
        resources: multipleMockResources,
        sortConfig,
        onSort,
        isFetching: false,
      });

      for (const row of container.querySelectorAll("tbody tr")) {
        expect(row.className).not.toMatch(/(^|[\s:])relative\b/);

        for (const cell of row.querySelectorAll("td")) {
          expect(cell.className).toMatch(/(^|\s)relative\b/);
        }
      }
    });

    it("covers every cell in a row with a link to that row's resource", () => {
      const { container } = renderTable({
        resources: multipleMockResources,
        sortConfig,
        onSort,
        isFetching: false,
      });

      const rows = [...container.querySelectorAll("tbody tr")];
      expect(rows).toHaveLength(multipleMockResources.length);

      rows.forEach((row, index) => {
        const href = `/oil-gas-fields/${multipleMockResources[index].id}`;

        for (const cell of row.querySelectorAll("td")) {
          const links = [...cell.querySelectorAll("a")];
          expect(links).toHaveLength(1);
          expect(links[0]).toHaveAttribute("href", href);
        }
      });
    });

    it("exposes a single focusable, named link per row", () => {
      const { container } = renderTable({
        resources: multipleMockResources,
        sortConfig,
        onSort,
        isFetching: false,
      });

      rowsAndNames(container).forEach(([row, name]) => {
        const focusable = [...row.querySelectorAll("a")].filter(
          (link) =>
            link.getAttribute("tabindex") !== "-1" &&
            link.getAttribute("aria-hidden") !== "true",
        );

        expect(focusable).toHaveLength(1);
        expect(focusable[0]).toHaveAccessibleName(name);
      });
    });
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
