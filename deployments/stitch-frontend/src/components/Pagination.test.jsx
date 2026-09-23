import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Pagination from "./Pagination";

const onPageChange = vi.fn();
const onPageSizeChange = vi.fn();

beforeEach(() => {
  onPageChange.mockClear();
  onPageSizeChange.mockClear();
});

function renderPagination(props) {
  return render(
    <Pagination
      pageSize={25}
      onPageChange={onPageChange}
      onPageSizeChange={onPageSizeChange}
      {...props}
    />,
  );
}

// Page buttons, in render order, excluding the prev/next arrows.
function pageButtons(container) {
  return [...container.querySelectorAll("button")].filter(
    (button) => !button.getAttribute("aria-label"),
  );
}

function visibleLabels(container) {
  return pageButtons(container)
    .filter((button) => button.style.visibility !== "hidden")
    .map((button) => button.textContent);
}

describe("Pagination", () => {
  describe("slot layout", () => {
    it("keeps a fixed number of page slots near the start", () => {
      const { container } = renderPagination({
        page: 2,
        totalCount: 2000,
        totalPages: 80,
      });

      expect(pageButtons(container)).toHaveLength(6);
      expect(visibleLabels(container)).toEqual(["1", "2", "3", "4", "5", "80"]);
    });

    it("shows the trailing run of pages near the end", () => {
      const { container } = renderPagination({
        page: 79,
        totalCount: 2000,
        totalPages: 80,
      });

      expect(visibleLabels(container)).toEqual([
        "1",
        "76",
        "77",
        "78",
        "79",
        "80",
      ]);
    });

    it("shows current page with both neighbours in the middle", () => {
      const { container } = renderPagination({
        page: 40,
        totalCount: 2000,
        totalPages: 80,
      });

      expect(visibleLabels(container)).toEqual(["1", "39", "40", "41", "80"]);
    });

    it("hides slots that have no corresponding page but keeps their space", () => {
      const { container } = renderPagination({
        page: 1,
        totalCount: 60,
        totalPages: 3,
      });

      expect(pageButtons(container)).toHaveLength(6);
      expect(visibleLabels(container)).toEqual(["1", "2", "3"]);

      const hidden = pageButtons(container).filter(
        (button) => button.style.visibility === "hidden",
      );
      for (const button of hidden) {
        expect(button).toHaveAttribute("tabindex", "-1");
      }
    });
  });

  describe("navigation", () => {
    it("marks the current page for assistive tech", () => {
      renderPagination({ page: 40, totalCount: 2000, totalPages: 80 });

      expect(screen.getByRole("button", { current: "page" })).toHaveTextContent(
        "40",
      );
    });

    it("disables prev on the first page and next on the last", () => {
      const { unmount } = renderPagination({
        page: 1,
        totalCount: 2000,
        totalPages: 80,
      });
      expect(screen.getByLabelText("Previous page")).toBeDisabled();
      expect(screen.getByLabelText("Next page")).toBeEnabled();
      unmount();

      renderPagination({ page: 80, totalCount: 2000, totalPages: 80 });
      expect(screen.getByLabelText("Previous page")).toBeEnabled();
      expect(screen.getByLabelText("Next page")).toBeDisabled();
    });

    it("reports the requested page when a slot is clicked", async () => {
      renderPagination({ page: 40, totalCount: 2000, totalPages: 80 });

      await userEvent.click(screen.getByRole("button", { name: "41" }));

      expect(onPageChange).toHaveBeenCalledWith(41);
    });
  });

  // STIT-739
  describe("large page counts", () => {
    it("formats page numbers with locale-aware thousands separators", () => {
      const { container } = renderPagination({
        page: 5000,
        totalCount: 249_975,
        totalPages: 9999,
      });

      expect(visibleLabels(container)).toEqual([
        "1",
        "4,999",
        "5,000",
        "5,001",
        "9,999",
      ]);
    });

    it("formats the result summary", () => {
      renderPagination({
        page: 10234,
        pageSize: 25,
        totalCount: 308_650,
        totalPages: 12346,
      });

      expect(
        screen.getByText("Showing 255,826–255,850 of 308,650"),
      ).toBeInTheDocument();
    });

    it("narrows the slot window past four digits to bound the control width", () => {
      const { container } = renderPagination({
        page: 6000,
        totalCount: 308_650,
        totalPages: 12346,
      });

      expect(pageButtons(container)).toHaveLength(3);
      expect(visibleLabels(container)).toEqual(["1", "6,000", "12,346"]);
    });

    it("keeps the wide window at the four-digit boundary", () => {
      const { container } = renderPagination({
        page: 5000,
        totalCount: 249_975,
        totalPages: 9999,
      });

      expect(pageButtons(container)).toHaveLength(5);
    });

    it("narrows the window as soon as page counts reach five digits", () => {
      const { container } = renderPagination({
        page: 5000,
        totalCount: 250_000,
        totalPages: 10000,
      });

      expect(pageButtons(container)).toHaveLength(3);
      expect(visibleLabels(container)).toEqual(["1", "5,000", "10,000"]);
    });

    it("still shows a trailing run of pages near the end", () => {
      const { container } = renderPagination({
        page: 12346,
        totalCount: 308_650,
        totalPages: 12346,
      });

      expect(visibleLabels(container)).toEqual([
        "1",
        "12,344",
        "12,345",
        "12,346",
      ]);
    });

    it("lets page buttons grow instead of pinning them to a fixed width", () => {
      const { container } = renderPagination({
        page: 10234,
        totalCount: 308_650,
        totalPages: 12346,
      });

      for (const button of pageButtons(container)) {
        expect(button.className).not.toMatch(/(^|\s)w-9(\s|$)/);
        expect(button.className).toMatch(/(^|\s)min-w-9(\s|$)/);
      }

      // The arrows carry a single glyph and stay square.
      expect(screen.getByLabelText("Next page").className).toMatch(
        /(^|\s)w-9(\s|$)/,
      );
    });

    // `min-w-9` replaces flexbox's `min-width: auto`, so without `shrink-0` a
    // narrow viewport squeezes the buttons back to 36px and clips the label.
    it("stops buttons being squeezed below their label, wrapping instead", () => {
      const { container } = renderPagination({
        page: 5000,
        totalCount: 249_975,
        totalPages: 9999,
      });

      for (const button of container.querySelectorAll("button")) {
        expect(button.className).toMatch(/(^|\s)shrink-0(\s|$)/);
      }

      for (const span of container.querySelectorAll(
        'span[aria-hidden="true"]',
      )) {
        expect(span.className).toMatch(/(^|\s)shrink-0(\s|$)/);
      }

      expect(
        screen.getByLabelText("Next page").parentElement.className,
      ).toMatch(/(^|\s)flex-wrap(\s|$)/);
    });
  });
});
