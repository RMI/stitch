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

function makeResources(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    data: { name: `Field ${index + 1}` },
    provenance: {},
  }));
}

describe("ResourcesTable", () => {
  it("renders nothing when there are no resources and nothing is loading", () => {
    const { container } = renderTable({
      resources: [],
      sortConfig,
      onSort,
      isLoading: false,
    });

    expect(container).toBeEmptyDOMElement();
  });

  it("renders real rows when resources are available", () => {
    renderTable({
      resources: mockResources,
      sortConfig,
      onSort,
      isLoading: false,
    });

    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
    expect(screen.queryAllByTestId("resource-skeleton-row")).toHaveLength(0);
  });

  it("shows no skeleton rows on the very first load, before any data has ever been shown", () => {
    const { container } = renderTable({
      resources: [],
      sortConfig,
      onSort,
      isLoading: true,
    });

    expect(container).toBeEmptyDOMElement();
  });

  it("shows skeleton rows matching the previously displayed row count when refetching", () => {
    const { rerender } = render(
      <MemoryRouter>
        <ResourcesTable
          resources={makeResources(10)}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={false}
        />
      </MemoryRouter>,
    );

    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={true}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByTestId("resource-skeleton-row")).toHaveLength(10);
  });

  it("shows fewer skeleton rows when the previous result set was smaller than a full page", () => {
    const { rerender } = render(
      <MemoryRouter>
        <ResourcesTable
          resources={makeResources(3)}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={false}
        />
      </MemoryRouter>,
    );

    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={true}
        />
      </MemoryRouter>,
    );

    expect(screen.getAllByTestId("resource-skeleton-row")).toHaveLength(3);
  });

  it("shows no skeleton rows after a confirmed empty result, even after previously having rows", () => {
    const { rerender, container } = render(
      <MemoryRouter>
        <ResourcesTable
          resources={makeResources(4)}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={false}
        />
      </MemoryRouter>,
    );

    // A filter change triggers a refetch: 4 skeleton rows, matching the
    // previous confirmed count.
    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={true}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByTestId("resource-skeleton-row")).toHaveLength(4);

    // The refetch settles on a genuinely empty result (0 matches).
    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={false}
        />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();

    // Applying another filter triggers another refetch: the previous
    // confirmed count was 0, so no skeleton rows should appear this time.
    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={true}
        />
      </MemoryRouter>,
    );
    expect(screen.queryAllByTestId("resource-skeleton-row")).toHaveLength(0);
  });

  it("announces the loading state to screen readers", () => {
    const { rerender } = render(
      <MemoryRouter>
        <ResourcesTable
          resources={mockResources}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={false}
        />
      </MemoryRouter>,
    );

    rerender(
      <MemoryRouter>
        <ResourcesTable
          resources={[]}
          sortConfig={sortConfig}
          onSort={onSort}
          isLoading={true}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/loading resources/i)).toBeInTheDocument();
  });

  it("keeps showing real rows during a background refetch rather than skeletons", () => {
    renderTable({
      resources: mockResources,
      sortConfig,
      onSort,
      isLoading: true,
    });

    expect(screen.getByText("Burgan Field")).toBeInTheDocument();
    expect(screen.queryAllByTestId("resource-skeleton-row")).toHaveLength(0);
  });
});
