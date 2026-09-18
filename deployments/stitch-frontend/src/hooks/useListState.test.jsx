import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { useListState } from "./useListState";

function Probe() {
  const { setFilters, setSort, setSearch, setPage, setPageSize } =
    useListState();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <>
      <output data-testid="url">{location.pathname + location.search}</output>
      <button onClick={() => setFilters({ country: ["NOR"] })}>filter</button>
      <button onClick={() => setSort({ column: "name", direction: "desc" })}>
        sort
      </button>
      <button onClick={() => setSearch("ghawar")}>search</button>
      <button onClick={() => setPage(3)}>page</button>
      <button onClick={() => setPageSize(25)}>pageSize</button>
      <button onClick={() => navigate(-1)}>back</button>
    </>
  );
}

function renderProbe(listUrl = "/") {
  return render(
    <MemoryRouter initialEntries={["/origin", listUrl]} initialIndex={1}>
      <Probe />
    </MemoryRouter>,
  );
}

const url = () => screen.getByTestId("url").textContent;

describe("useListState", () => {
  it("writes filters to the URL", () => {
    renderProbe();
    fireEvent.click(screen.getByText("filter"));
    expect(url()).toBe("/?country=NOR");
  });

  it.each([["filter"], ["sort"], ["search"]])(
    "replaces the history entry when %s changes",
    (action) => {
      renderProbe();
      fireEvent.click(screen.getByText(action));
      fireEvent.click(screen.getByText("back"));
      expect(url()).toBe("/origin");
    },
  );

  it("pushes a history entry when the page changes", () => {
    renderProbe();
    fireEvent.click(screen.getByText("page"));
    expect(url()).toBe("/?page=3");
    fireEvent.click(screen.getByText("back"));
    expect(url()).toBe("/");
  });

  it("pushes a history entry and resets to page 1 when page size changes", () => {
    renderProbe("/?page=4");
    fireEvent.click(screen.getByText("pageSize"));
    // Should reset to page 1, so page=4 is gone
    expect(url()).not.toContain("page=4");
    // Back should return to the pre-action state (proves it pushed, not replaced)
    fireEvent.click(screen.getByText("back"));
    expect(url()).toBe("/?page=4");
  });

  it.each([["filter"], ["sort"], ["search"]])(
    "resets to page 1 when %s changes",
    (action) => {
      renderProbe("/?page=4");
      fireEvent.click(screen.getByText(action));
      expect(url()).not.toContain("page=4");
    },
  );

  it("preserves the rest of the state when one part changes", () => {
    renderProbe("/?q=ghawar&sort_by=name&sort_order=desc");
    fireEvent.click(screen.getByText("filter"));
    expect(url()).toContain("q=ghawar");
    expect(url()).toContain("sort_by=name");
    expect(url()).toContain("country=NOR");
  });
});
