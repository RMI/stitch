import { afterEach, describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { useListState } from "./useListState";
import { PAGE_SIZE_STORAGE_KEY } from "../config/pageSizePreference";

function Probe() {
  const { pageSize, setFilters, setSort, setSearch, setPage, setPageSize } =
    useListState();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <>
      <output data-testid="url">{location.pathname + location.search}</output>
      <output data-testid="pageSize">{pageSize}</output>
      <button onClick={() => setFilters({ country: ["NOR"] })}>filter</button>
      <button onClick={() => setSort({ column: "name", direction: "desc" })}>
        sort
      </button>
      <button onClick={() => setSearch("ghawar")}>search</button>
      <button onClick={() => setPage(3)}>page</button>
      <button onClick={() => setPageSize(25)}>pageSize</button>
      <button onClick={() => navigate(-1)}>back</button>
      {/* What the Resources tab and logotype do: a bare list URL. */}
      <button onClick={() => navigate("/")}>resources tab</button>
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
const pageSize = () => screen.getByTestId("pageSize").textContent;

afterEach(() => {
  window.sessionStorage.clear();
});

describe("useListState", () => {
  it("writes filters to the URL", () => {
    renderProbe();
    fireEvent.click(screen.getByText("filter"));
    // page_size rides along with any other state, so the link is exact.
    expect(url()).toBe("/?page_size=10&country=NOR");
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
    expect(url()).toBe("/?page=3&page_size=10");
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

  describe("remembered page size", () => {
    it("uses the default page size on a first visit", () => {
      renderProbe("/");
      expect(pageSize()).toBe("10");
    });

    it("keeps the chosen page size after returning to a bare list URL", () => {
      renderProbe("/");
      fireEvent.click(screen.getByText("pageSize"));
      expect(url()).toBe("/?page_size=25");

      fireEvent.click(screen.getByText("resources tab"));

      expect(url()).toBe("/");
      expect(pageSize()).toBe("25");
    });

    it("writes the remembered size into the URL on the next change", () => {
      window.sessionStorage.setItem(PAGE_SIZE_STORAGE_KEY, "50");
      renderProbe("/");
      fireEvent.click(screen.getByText("filter"));
      expect(url()).toBe("/?page_size=50&country=NOR");
    });

    it("lets a page_size in the URL win without changing what is remembered", () => {
      window.sessionStorage.setItem(PAGE_SIZE_STORAGE_KEY, "50");
      renderProbe("/?page_size=100");

      expect(pageSize()).toBe("100");
      expect(window.sessionStorage.getItem(PAGE_SIZE_STORAGE_KEY)).toBe("50");
    });

    it("keeps an explicit page_size=10 from a URL when something else changes", () => {
      window.sessionStorage.setItem(PAGE_SIZE_STORAGE_KEY, "50");
      renderProbe("/?page_size=10");
      fireEvent.click(screen.getByText("filter"));

      expect(url()).toBe("/?page_size=10&country=NOR");
      expect(pageSize()).toBe("10");
    });
  });
});
