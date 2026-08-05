import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import MergeCandidateReviewPage from "./MergeCandidateReviewPage";
import { useMergeCandidates, useMergeCandidate } from "../hooks/useResources";
import { reviewMergeCandidate, getResourceDetail } from "../queries/api";

vi.mock("../hooks/useResources", () => ({
  useMergeCandidates: vi.fn(),
  useMergeCandidate: vi.fn(),
}));

vi.mock("../queries/api", () => ({
  reviewMergeCandidate: vi.fn(),
  getResourceDetail: vi.fn(),
}));

vi.mock("../components/MergeSourceComparison", () => ({
  default: ({ resourceIds, compare, isLoading }) => (
    <div>
      Source comparison for {resourceIds.join(", ")}
      {compare ? " (compare loaded)" : isLoading ? " (loading)" : ""}
    </div>
  ),
}));

vi.mock("../components/MergedResourceView", () => ({
  default: ({ resourceId }) => <div>Merged resource {resourceId}</div>,
}));

const candidates = [
  {
    id: 11,
    status: "PENDING",
    resource_ids: [101, 102],
    merged_resource_id: null,
  },
  {
    id: 12,
    status: "APPROVED",
    resource_ids: [201, 202],
    merged_resource_id: 301,
  },
];

const pendingCandidate = candidates[0];

// Detail responses layer `compare` on top of the list schema. The panel
// heading must come from this, not from per-resource fetches.
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
const nextPendingCandidate = {
  id: 13,
  status: "PENDING",
  resource_ids: [301, 302],
  merged_resource_id: null,
};

const defaultHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

// 101/102 are two spellings of the same field. "wm" outranks "gem" in
// SOURCE_PRIORITY, so the resolved name is the wm spelling ("Bergan") even
// though the gem resource comes first — priority wins over resource order.
const resourceDetailsById = {
  101: { data: { name: "Burgan" }, provenance: { name: "gem" } },
  102: { data: { name: "Bergan" }, provenance: { name: "wm" } },
  201: { data: { name: "Arabian Consolidated" }, provenance: { name: "rmi" } },
  202: { data: { name: "Arabian Duplicate" }, provenance: { name: "gem" } },
  301: { data: { name: "Arabian Merged" }, provenance: { name: "rmi" } },
};

beforeEach(() => {
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  vi.mocked(useMergeCandidates).mockReturnValue({
    ...defaultHookReturn,
    data: candidates,
    refetch: vi.fn(),
  });
  vi.mocked(useMergeCandidate).mockReturnValue({
    ...defaultHookReturn,
    data: pendingDetail,
    refetch: vi.fn(),
  });
  vi.mocked(reviewMergeCandidate).mockResolvedValue({});
  vi.mocked(getResourceDetail).mockImplementation((_config, id) =>
    Promise.resolve(resourceDetailsById[id]),
  );
});

describe("MergeCandidateReviewPage", () => {
  it("centers the page on a queue and one decision panel", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByRole("heading", { name: "Merge Review" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Queue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Burgan" })).toBeInTheDocument();

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

  it("shows the resolved candidate name in the queue, hiding raw resource ids", async () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    const queueItem = await screen.findByRole("button", { name: /Bergan/ });
    expect(within(queueItem).queryByText(/101/)).not.toBeInTheDocument();
    expect(within(queueItem).queryByText(/Resources/)).not.toBeInTheDocument();
    expect(within(queueItem).queryByText(/Merged/)).not.toBeInTheDocument();
    expect(queueItem).toHaveAttribute("title", "Source resources: 101, 102");
  });

  it("falls back to the candidate id when the compare object has no name", () => {
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: { ...pendingCandidate, compare: [] },
    });
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      screen.getByRole("heading", { name: "Candidate #11" }),
    ).toBeInTheDocument();
  });

  it('labels a pending item\'s status badge "CANDIDATE" instead of "PENDING"', async () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    const pendingItem = await screen.findByRole("button", { name: /Bergan/ });
    expect(within(pendingItem).getByText("CANDIDATE")).toBeInTheDocument();
    expect(within(pendingItem).queryByText("PENDING")).not.toBeInTheDocument();

    const approvedItem = await screen.findByRole("button", {
      name: /Arabian Consolidated/,
    });
    expect(within(approvedItem).getByText("APPROVED")).toBeInTheDocument();
  });

  it("shows the compare-derived name in the detail panel heading", () => {
    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      await screen.findByRole("heading", { name: "Bergan" }),
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

  it("advances to the next pending candidate and clears notes after review", async () => {
    const user = userEvent.setup();
    vi.mocked(useMergeCandidates).mockReturnValue({
      ...defaultHookReturn,
      data: [pendingCandidate, nextPendingCandidate, candidates[1]],
    });
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

    expect(
      screen.getByRole("heading", { name: "Candidate #11" }),
    ).toBeInTheDocument();
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
      await screen.findByRole("heading", { name: "Burgan" }),
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

    expect(
      screen.getByRole("heading", { name: "Candidate #11" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve merge" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/could not be refreshed/)).toBeInTheDocument();
    expect(screen.getByText(/detail boom/)).toBeInTheDocument();
  });

  it("shows the merged resource instead of the source comparison once merged_resource_id is set", () => {
    const mergedCandidate = candidates[1];
    vi.mocked(useMergeCandidates).mockReturnValue({
      ...defaultHookReturn,
      data: [mergedCandidate],
    });
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: mergedCandidate,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(screen.getByText("Merged resource 301")).toBeInTheDocument();
    expect(
      screen.queryByText("Source comparison for 201, 202"),
    ).not.toBeInTheDocument();
  });

  it("shows the merged resource's name in the heading once merged", async () => {
    const mergedCandidate = candidates[1];
    vi.mocked(useMergeCandidates).mockReturnValue({
      ...defaultHookReturn,
      data: [mergedCandidate],
    });
    // Post-merge, the originals are null shells: compare carries no name.
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: { ...mergedCandidate, compare: [] },
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(
      await screen.findByRole("heading", { name: "Arabian Merged" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Candidate #12" }),
    ).not.toBeInTheDocument();
  });

  it("links the merged resource id to its detail page", () => {
    const mergedCandidate = candidates[1];
    vi.mocked(useMergeCandidates).mockReturnValue({
      ...defaultHookReturn,
      data: [mergedCandidate],
    });
    vi.mocked(useMergeCandidate).mockReturnValue({
      ...defaultHookReturn,
      data: mergedCandidate,
    });

    renderWithQueryClient(<MergeCandidateReviewPage />);

    expect(screen.getByRole("link", { name: "301" })).toHaveAttribute(
      "href",
      "/oil-gas-fields/301",
    );
  });

  it("blocks with an error when the detail query fails and the queue has no item", () => {
    vi.mocked(useMergeCandidates).mockReturnValue({
      ...defaultHookReturn,
      data: [],
      refetch: vi.fn(),
    });
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
});
