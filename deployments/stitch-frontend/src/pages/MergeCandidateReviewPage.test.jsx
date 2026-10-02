import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import MergeCandidateReviewPage from "./MergeCandidateReviewPage";
import { useMergeCandidates, useMergeCandidate } from "../hooks/useResources";
import { reviewMergeCandidate, getResourceDetail } from "../queries/api";

// Mock only the read hooks; the review path exercises the real
// useReviewMergeCandidate mutation against the mocked API module.
vi.mock("../hooks/useResources", async (importOriginal) => ({
  ...(await importOriginal()),
  useMergeCandidates: vi.fn(),
  useMergeCandidate: vi.fn(),
}));

vi.mock("../queries/api", () => ({
  reviewMergeCandidate: vi.fn(),
  getResourceDetail: vi.fn(),
}));

vi.mock("../components/MergeSourceComparison", () => ({
  default: ({ resourceIds, compare, isLoading, sourceDetails }) => (
    <div>
      Source comparison for {resourceIds.join(", ")}
      {compare ? " (compare loaded)" : isLoading ? " (loading)" : ""}
      {sourceDetails?.data ? (
        <span>
          {" "}
          (name sources:{" "}
          {sourceDetails.data.map((d) => d?.provenance?.name).join(", ")})
        </span>
      ) : null}
    </div>
  ),
}));

vi.mock("../components/MergedResourceView", () => ({
  default: ({ resourceId }) => <div>Merged resource {resourceId}</div>,
}));

const candidates = [
  {
    id: 11,
    name: "Bergan",
    status: "PENDING",
    resource_ids: [101, 102],
    merged_resource_id: null,
  },
  {
    id: 12,
    name: "Arabian Merged",
    status: "APPROVED",
    resource_ids: [201, 202],
    merged_resource_id: 301,
  },
];

const pendingCandidate = candidates[0];

// Detail responses layer `compare` on top of the list schema.
const pendingDetail = {
  ...pendingCandidate,
  compare: [
    {
      field: "name",
      status: "different",
      values: [
        {
          source: "gem",
          source_id: 1,
          value: "Burgan",
          priority: 0,
          resource_id: 101,
        },
        {
          source: "wm",
          source_id: 2,
          value: "Bergan",
          priority: 1,
          resource_id: 102,
        },
      ],
    },
  ],
};
// No licensed source carries a name, so the UI falls back to the id.
const nextPendingCandidate = {
  id: 13,
  name: null,
  status: "PENDING",
  resource_ids: [301, 302],
  merged_resource_id: null,
};

// Every status, so approved candidates are listed too.
const ALL_STATUSES_URL = "/?status=all";

const defaultHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

// Stands in for the list endpoint: applies the requested status filter,
// returns the requested page, and counts the whole queue by status, as the API
// does. (Sorting is the API's job; tests check the params sent instead.)
function mockQueue(allCandidates) {
  vi.mocked(useMergeCandidates).mockImplementation((_endpoint, params) => {
    const page = params?.page ?? 1;
    const pageSize = params?.page_size ?? 25;
    const matching = allCandidates.filter(
      (c) => !params?.status || params.status.includes(c.status),
    );
    const countOf = (status) =>
      allCandidates.filter((c) => c.status === status).length;
    return {
      ...defaultHookReturn,
      data: {
        items: matching.slice((page - 1) * pageSize, page * pageSize),
        total_count: matching.length,
        page,
        page_size: pageSize,
        total_pages: Math.ceil(matching.length / pageSize),
        status_counts: {
          PENDING: countOf("PENDING"),
          APPROVED: countOf("APPROVED"),
          DENIED: countOf("DENIED"),
        },
      },
      refetch: vi.fn(),
    };
  });
}

// The params of the most recent list request.
function lastQueueRequest() {
  return vi.mocked(useMergeCandidates).mock.lastCall[1];
}

beforeEach(() => {
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  mockQueue(candidates);
  vi.mocked(useMergeCandidate).mockReturnValue({
    ...defaultHookReturn,
    data: pendingDetail,
    refetch: vi.fn(),
  });
  vi.mocked(reviewMergeCandidate).mockResolvedValue({});
});

describe("MergeCandidateReviewPage", () => {
  it("centers the page on a queue and one decision panel", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByRole("heading", { name: "Merge review" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Queue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bergan" })).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", { name: "Summary" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Review one candidate at a time."),
    ).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
  });

  it("puts the candidate panel before the queue in reading order", () => {
    // On one-column screens the panel is shown first. Keeping that order in
    // the DOM (not just visually) means screen readers and keyboard focus
    // meet the candidate before the queue, matching what is on screen.
    renderWithQueryClient(<MergeCandidateReviewPage />);

    const panel = screen.getByRole("article");
    const queue = screen
      .getByRole("heading", { name: "Queue" })
      .closest("aside");

    expect(
      panel.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  describe("selecting a candidate", () => {
    // jsdom has neither matchMedia nor scrollIntoView, so each test stubs the
    // layout it needs: two columns (md and up) or one.
    let scrollIntoView;

    function useLayout({ twoColumns }) {
      vi.stubGlobal(
        "matchMedia",
        vi.fn((query) => ({ matches: twoColumns, media: query })),
      );
    }

    async function selectCandidate13() {
      const user = userEvent.setup();
      mockQueue([pendingCandidate, nextPendingCandidate]);
      vi.mocked(useMergeCandidate).mockImplementation((_endpoint, id) => ({
        ...defaultHookReturn,
        data:
          id === nextPendingCandidate.id ? nextPendingCandidate : pendingDetail,
      }));

      renderWithQueryClient(<MergeCandidateReviewPage />);

      const queue = screen
        .getByRole("heading", { name: "Queue" })
        .closest("aside");
      await user.click(
        within(queue).getByRole("button", { name: /Candidate #13/ }),
      );
      return user;
    }

    beforeEach(() => {
      scrollIntoView = vi.fn();
      Element.prototype.scrollIntoView = scrollIntoView;
    });

    afterEach(() => {
      vi.unstubAllGlobals();
      delete Element.prototype.scrollIntoView;
    });

    it("moves focus to the candidate panel", async () => {
      // The panel precedes the queue in the DOM, so without this, Tab from the
      // chosen queue item would move away from its decision controls.
      useLayout({ twoColumns: true });
      const user = await selectCandidate13();

      const panel = screen.getByRole("region", { name: "Selected candidate" });
      expect(panel).toHaveFocus();

      // The next Tab lands inside the panel, on the way to Deny/Approve.
      await user.tab();
      expect(panel).toContainElement(document.activeElement);
    });

    it("does not scroll the page in the two-column layout", async () => {
      // The panel is beside the queue, so scrolling would only make the page
      // jump under the reviewer's pointer.
      useLayout({ twoColumns: true });
      await selectCandidate13();

      expect(scrollIntoView).not.toHaveBeenCalled();
    });

    it("scrolls the panel into view in the one-column layout", async () => {
      // The panel sits above the queue, so without this the change happens
      // off-screen.
      useLayout({ twoColumns: false });
      await selectCandidate13();

      expect(
        screen.getByRole("region", { name: "Selected candidate" }),
      ).toHaveFocus();
      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect(scrollIntoView.mock.contexts[0]).toBe(
        screen.getByRole("region", { name: "Selected candidate" }),
      );
    });

    it("does not move focus or scroll on first load", () => {
      useLayout({ twoColumns: false });
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(
        screen.getByRole("region", { name: "Selected candidate" }),
      ).not.toHaveFocus();
      expect(scrollIntoView).not.toHaveBeenCalled();
    });
  });

  it("shows the API's candidate name in the queue, hiding raw resource ids", async () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    const queueItem = await screen.findByRole("button", { name: /Bergan/ });
    expect(within(queueItem).queryByText(/101/)).not.toBeInTheDocument();
    expect(within(queueItem).queryByText(/Resources/)).not.toBeInTheDocument();
    expect(within(queueItem).queryByText(/Merged/)).not.toBeInTheDocument();
    expect(queueItem).toHaveAttribute("title", "Source resources: 101, 102");
  });

  it("falls back to the candidate id when the API has no name", () => {
    mockQueue([{ ...pendingCandidate, name: null }]);
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: { ...pendingCandidate, name: null, compare: [] },
    });
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByRole("heading", { name: "Candidate #11" }),
    ).toBeInTheDocument();
  });

  it('labels a pending item\'s status badge "CANDIDATE" instead of "PENDING"', async () => {
    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    const pendingItem = await screen.findByRole("button", { name: /Bergan/ });
    expect(within(pendingItem).getByText("CANDIDATE")).toBeInTheDocument();
    expect(within(pendingItem).queryByText("PENDING")).not.toBeInTheDocument();

    const approvedItem = await screen.findByRole("button", {
      name: /Arabian Merged/,
    });
    expect(within(approvedItem).getByText("APPROVED")).toBeInTheDocument();
  });

  it("names queue rows without fetching each resource", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    expect(
      screen.getByRole("button", { name: /Arabian Merged/ }),
    ).toBeInTheDocument();
    // Only the selected candidate's resources are fetched, for its source
    // mix; the other rows' resources (201, 202, 301) are not.
    const fetchedIds = vi
      .mocked(getResourceDetail)
      .mock.calls.map(([, id]) => id);
    expect(new Set(fetchedIds)).toEqual(new Set([101, 102]));
  });

  it("shows the detail's name in the panel heading once it loads", () => {
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: { ...pendingDetail, name: "Bergan (refreshed)" },
    });
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByRole("heading", { name: "Bergan (refreshed)" }),
    ).toBeInTheDocument();
  });

  it("links each source resource id to its detail page", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(screen.getByRole("link", { name: "101" })).toHaveAttribute(
      "href",
      "/oil-gas-fields/101",
    );
    expect(screen.getByRole("link", { name: "102" })).toHaveAttribute(
      "href",
      "/oil-gas-fields/102",
    );
  });

  it("gives the source comparison each resource's source details", async () => {
    vi.mocked(getResourceDetail).mockImplementation((_config, id) =>
      Promise.resolve(
        {
          101: { provenance: { name: "gem" } },
          102: { provenance: { name: "wm" } },
        }[id],
      ),
    );
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      await screen.findByText(/\(name sources: gem, wm\)/),
    ).toBeInTheDocument();
  });

  it("shows the source comparison instead of the merged preview", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    const comparison = screen.getByText(
      "Source comparison for 101, 102 (compare loaded)",
    );
    const decisionNotes = screen.getByLabelText("Decision notes");

    expect(
      screen.getByRole("button", { name: "Approve merge" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Deny merge" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Merged preview")).not.toBeInTheDocument();
    expect(screen.queryByText("Source resources (2)")).not.toBeInTheDocument();
    expect(comparison.compareDocumentPosition(decisionNotes)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("submits the selected review decision with notes", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<MergeCandidateReviewPage />);

    await user.type(screen.getByLabelText("Decision notes"), "Looks safe");
    await user.click(screen.getByRole("button", { name: "Approve merge" }));

    await waitFor(() => {
      expect(reviewMergeCandidate).toHaveBeenCalledWith(
        expect.any(Object),
        11,
        "approve",
        expect.any(Function),
        "oil-gas-fields",
        "Looks safe",
      );
    });
  });

  it("refreshes all cached oil-gas-fields data after a review", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderWithQueryClient(<MergeCandidateReviewPage />);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.click(screen.getByRole("button", { name: "Approve merge" }));

    // An approved merge changes the resources themselves, so everything under
    // the endpoint (lists, details, merge candidates) must be refetched.
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["oil-gas-fields"],
      });
    });
  });

  it("advances to the next pending candidate and clears notes after review", async () => {
    const user = userEvent.setup();
    mockQueue([pendingCandidate, nextPendingCandidate, candidates[1]]);
    vi.mocked(useMergeCandidate).mockImplementation((_endpoint, id) => ({
      ...defaultHookReturn,
      data:
        id === nextPendingCandidate.id
          ? nextPendingCandidate
          : pendingCandidate,
    }));

    renderWithQueryClient(<MergeCandidateReviewPage />);

    await user.type(screen.getByLabelText("Decision notes"), "Done reviewing");
    await user.click(screen.getByRole("button", { name: "Approve merge" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Candidate #13" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Decision notes")).toHaveValue("");
  });

  it("keeps the candidate panel in place while the detail query loads", () => {
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: null,
      isLoading: true,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(screen.getByRole("heading", { name: "Bergan" })).toBeInTheDocument();
    expect(
      screen.getByText("Source comparison for 101, 102 (loading)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve merge" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading candidate…")).not.toBeInTheDocument();
  });

  it("shows the queue-cached name while the detail query loads, not the id fallback", async () => {
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: null,
      isLoading: true,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      await screen.findByRole("heading", { name: "Bergan" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Candidate #11" }),
    ).not.toBeInTheDocument();
  });

  it("approves with the queue's candidate id while the detail query loads", async () => {
    const user = userEvent.setup();
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: null,
      isLoading: true,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);
    await user.click(screen.getByRole("button", { name: "Approve merge" }));

    await waitFor(() => {
      expect(reviewMergeCandidate).toHaveBeenCalledWith(
        expect.any(Object),
        11,
        "approve",
        expect.any(Function),
        "oil-gas-fields",
        "",
      );
    });
  });

  it("renders the panel with a banner when the detail query fails", () => {
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: null,
      isError: true,
      error: new Error("detail boom"),
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(screen.getByRole("heading", { name: "Bergan" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve merge" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/could not be refreshed/)).toBeInTheDocument();
    expect(screen.getByText(/detail boom/)).toBeInTheDocument();
  });

  it("shows the merged resource instead of the source comparison once merged_resource_id is set", async () => {
    const mergedCandidate = candidates[1];
    mockQueue([mergedCandidate]);
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: mergedCandidate,
    });

    // The only candidate is approved, which the default (pending) view hides.
    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    expect(screen.getByText("Merged resource 301")).toBeInTheDocument();
    expect(
      screen.queryByText("Source comparison for 201, 202"),
    ).not.toBeInTheDocument();
  });

  it("does not fetch source details for an already-merged candidate", () => {
    const mergedCandidate = candidates[1];
    mockQueue([mergedCandidate]);
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: mergedCandidate,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    // The merged resource replaces the comparison, so its source mix is unused.
    expect(screen.getByText("Merged resource 301")).toBeInTheDocument();
    expect(getResourceDetail).not.toHaveBeenCalled();
  });

  it("shows the merged resource's name in the heading once merged", async () => {
    const mergedCandidate = candidates[1];
    mockQueue([mergedCandidate]);
    // Post-merge, the originals are null shells: compare carries no name.
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: { ...mergedCandidate, compare: [] },
    });

    // The only candidate is approved, which the default (pending) view hides.
    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    expect(
      await screen.findByRole("heading", { name: "Arabian Merged" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Candidate #12" }),
    ).not.toBeInTheDocument();
  });

  it("links the merged resource id to its detail page", async () => {
    const mergedCandidate = candidates[1];
    mockQueue([mergedCandidate]);
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: mergedCandidate,
    });

    // The only candidate is approved, which the default (pending) view hides.
    renderWithQueryClient(<MergeCandidateReviewPage />, {
      initialEntries: [ALL_STATUSES_URL],
    });

    expect(screen.getByRole("link", { name: "301" })).toHaveAttribute(
      "href",
      "/oil-gas-fields/301",
    );
  });

  it("blocks with an error when the detail query fails and the queue has no item", () => {
    mockQueue([]);
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: null,
      isError: true,
      error: new Error("detail boom"),
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByText("No merge candidates to review."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Candidate #11" }),
    ).not.toBeInTheDocument();
  });

  describe("queue view", () => {
    const deniedCandidate = {
      id: 14,
      name: "Safaniya",
      status: "DENIED",
      resource_ids: [401, 402],
      merged_resource_id: null,
    };
    const approvedCandidate = candidates[1];

    function queue() {
      return screen.getByRole("heading", { name: "Queue" }).closest("aside");
    }

    // Queue rows are the toggle buttons; the queue also holds the filter and
    // paging buttons.
    function queueItems() {
      return within(queue())
        .queryAllByRole("button")
        .filter((button) => button.hasAttribute("aria-pressed"));
    }

    // The header counts live in a <dt>/<dd> pair; read the value beside a label.
    function countFor(label) {
      const header = screen
        .getByRole("heading", { name: "Merge review" })
        .closest("header");
      return within(header).getByText(label).parentElement.querySelector("dd")
        .textContent;
    }

    async function toggleStatus(user, label) {
      await user.click(
        within(queue()).getByRole("button", { name: /^Status/ }),
      );
      await user.click(
        screen.getByRole("checkbox", { name: new RegExp(label) }),
      );
    }

    function manyPending(count) {
      return Array.from({ length: count }, (_, i) => ({
        id: 100 + i,
        name: `Field ${i + 1}`,
        status: "PENDING",
        resource_ids: [1000 + 2 * i, 1001 + 2 * i],
        merged_resource_id: null,
      }));
    }

    beforeEach(() => {
      mockQueue([pendingCandidate, deniedCandidate, approvedCandidate]);
    });

    it("lists only pending candidates by default", () => {
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(lastQueueRequest()).toEqual({
        page: 1,
        page_size: 25,
        status: ["PENDING"],
        sort_by: "created",
        sort_order: "desc",
      });
      expect(queueItems()).toHaveLength(1);
      expect(queueItems()[0]).toHaveAccessibleName(/Bergan/);
    });

    it("adds the statuses chosen in the Status filter", async () => {
      const user = userEvent.setup();
      renderWithQueryClient(<MergeCandidateReviewPage />);

      await toggleStatus(user, "Approved");

      expect(lastQueueRequest().status).toEqual(["PENDING", "APPROVED"]);
      expect(queueItems()).toHaveLength(2);
    });

    it("lists every status once none is selected", async () => {
      const user = userEvent.setup();
      renderWithQueryClient(<MergeCandidateReviewPage />);

      await toggleStatus(user, "Pending");

      expect(lastQueueRequest().status).toBeUndefined();
      expect(queueItems()).toHaveLength(3);
    });

    it("counts all candidates in the header regardless of the filter", async () => {
      const user = userEvent.setup();
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(countFor("Pending")).toBe("1");
      expect(countFor("Reviewed")).toBe("2");
      expect(countFor("Total")).toBe("3");

      await toggleStatus(user, "Denied");

      expect(countFor("Pending")).toBe("1");
      expect(countFor("Reviewed")).toBe("2");
      expect(countFor("Total")).toBe("3");
    });

    it("sends the chosen sort to the API", async () => {
      const user = userEvent.setup();
      renderWithQueryClient(<MergeCandidateReviewPage />);

      await user.selectOptions(
        screen.getByLabelText("Sort candidates"),
        "Recently reviewed",
      );

      expect(lastQueueRequest()).toMatchObject({
        page: 1,
        sort_by: "reviewed_at",
        sort_order: "desc",
      });
    });

    it("opens the view a URL describes", () => {
      renderWithQueryClient(<MergeCandidateReviewPage />, {
        initialEntries: [
          "/?page=2&page_size=10&status=APPROVED&status=DENIED&sort_by=created&sort_order=asc",
        ],
      });

      // The first request; this small fixture then steps back from page 2.
      expect(vi.mocked(useMergeCandidates).mock.calls[0][1]).toEqual({
        page: 2,
        page_size: 10,
        status: ["APPROVED", "DENIED"],
        sort_by: "created",
        sort_order: "asc",
      });
    });

    it("pages through the queue and selects a candidate on the new page", async () => {
      const user = userEvent.setup();
      mockQueue(manyPending(30));
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(queueItems()).toHaveLength(25);
      expect(
        screen.getByRole("button", { name: /^Field 1(?!\d)/ }),
      ).toHaveAttribute("aria-pressed", "true");

      await user.click(screen.getByRole("button", { name: "Next page" }));

      expect(lastQueueRequest().page).toBe(2);
      expect(queueItems()).toHaveLength(5);
      expect(screen.getByRole("button", { name: /Field 26/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    it("steps back to the last page when the page is past the end", async () => {
      mockQueue(manyPending(3));
      renderWithQueryClient(<MergeCandidateReviewPage />, {
        initialEntries: ["/?page=4"],
      });

      await waitFor(() => expect(lastQueueRequest().page).toBe(1));
      expect(queueItems()).toHaveLength(3);
    });

    it("returns to page 1 when a page past the end has no results", async () => {
      mockQueue([]);
      renderWithQueryClient(<MergeCandidateReviewPage />, {
        initialEntries: ["/?page=4"],
      });

      await waitFor(() => expect(lastQueueRequest().page).toBe(1));
    });

    it("clears the selection when the page comes back empty", async () => {
      const user = userEvent.setup();
      mockQueue([pendingCandidate, deniedCandidate]);
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(
        screen.getByRole("heading", { name: "Bergan" }),
      ).toBeInTheDocument();

      // Only approved candidates, of which there are none.
      await toggleStatus(user, "Approved");
      await user.click(screen.getByRole("checkbox", { name: /Pending/ }));

      expect(lastQueueRequest().status).toEqual(["APPROVED"]);
      expect(screen.getByText("Select a candidate.")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Approve merge" }),
      ).not.toBeInTheDocument();
    });

    it("selects the first pending candidate on the page", () => {
      mockQueue([approvedCandidate, deniedCandidate, pendingCandidate]);
      renderWithQueryClient(<MergeCandidateReviewPage />, {
        initialEntries: [ALL_STATUSES_URL],
      });

      expect(screen.getByRole("button", { name: /Bergan/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    describe("search", () => {
      function searchBox() {
        return within(queue()).getByRole("searchbox", {
          name: "Search candidates",
        });
      }

      it("sends the trimmed search on submit and returns to page 1", async () => {
        const user = userEvent.setup();
        renderWithQueryClient(<MergeCandidateReviewPage />, {
          initialEntries: ["/?page=2"],
        });

        await user.type(searchBox(), "  ghawar  ");
        // Typing alone does not search.
        expect(lastQueueRequest().q).toBeUndefined();

        await user.click(
          within(queue()).getByRole("button", { name: "Search" }),
        );

        expect(lastQueueRequest()).toMatchObject({ q: "ghawar", page: 1 });
        expect(searchBox()).toHaveValue("ghawar");
      });

      it("searches on Enter", async () => {
        const user = userEvent.setup();
        renderWithQueryClient(<MergeCandidateReviewPage />);

        await user.type(searchBox(), "12345{Enter}");

        expect(lastQueueRequest().q).toBe("12345");
      });

      it("clears the search with the clear button or by emptying the box", async () => {
        const user = userEvent.setup();
        renderWithQueryClient(<MergeCandidateReviewPage />, {
          initialEntries: ["/?q=ghawar"],
        });

        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(lastQueueRequest().q).toBeUndefined();
        expect(searchBox()).toHaveValue("");

        await user.type(searchBox(), "x{Enter}");
        expect(lastQueueRequest().q).toBe("x");
        await user.clear(searchBox());
        expect(lastQueueRequest().q).toBeUndefined();
      });

      it("opens with the URL's search in the box", () => {
        renderWithQueryClient(<MergeCandidateReviewPage />, {
          initialEntries: ["/?q=ghawar"],
        });

        expect(searchBox()).toHaveValue("ghawar");
        expect(lastQueueRequest().q).toBe("ghawar");
      });

      it("explains an empty queue caused by the search", () => {
        mockQueue([]);
        renderWithQueryClient(<MergeCandidateReviewPage />, {
          initialEntries: ["/?q=nothing-matches"],
        });

        expect(
          screen.getByText(/No candidates match this search/),
        ).toBeInTheDocument();
      });
    });

    it("explains an empty queue caused by the filter", () => {
      mockQueue([approvedCandidate]);
      renderWithQueryClient(<MergeCandidateReviewPage />);

      expect(
        screen.getByText(/No candidates match the selected statuses/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("No merge candidates to review."),
      ).not.toBeInTheDocument();
    });
  });
});
