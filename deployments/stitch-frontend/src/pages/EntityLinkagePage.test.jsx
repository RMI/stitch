import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EntityLinkagePage from "./EntityLinkagePage";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

const RUNNING_RECORD = {
  job_id: "job-123",
  state: "running",
  dedup_key: "LinkageParams:abc",
  initiated_by: "Test User",
  params: { apply_merges: false, page: 1, page_size: 50, max_pages: null },
  started_at: "2026-01-01T00:00:00Z",
  finished_at: null,
  result: null,
  error: null,
};

const SUCCEEDED_RECORD = {
  ...RUNNING_RECORD,
  state: "succeeded",
  finished_at: "2026-01-01T00:00:05Z",
  result: {
    pages_fetched: 1,
    total_records_fetched: 4,
    duplicate_name_candidate_count: 4,
    detail_records_fetched: 4,
    match_groups: [
      [101, 102],
      [203, 204, 205],
    ],
    merge_results: [],
  },
};

function mockResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

describe("EntityLinkagePage", () => {
  let getAccessTokenSilently;

  beforeEach(() => {
    getAccessTokenSilently = vi.fn().mockResolvedValue("test-access-token");
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      getAccessTokenSilently,
    });
  });

  it("starts a job (202) and authenticates the start request", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(mockResponse(202, RUNNING_RECORD));

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(screen.getByText("running")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Run in progress — refresh to check for the result."),
    ).toBeInTheDocument();

    const [startUrl, startOptions] = fetchSpy.mock.calls[0];
    expect(startUrl).toMatch(/\/start$/);
    expect(startOptions.method).toBe("POST");
    expect(startOptions.headers.Authorization).toBe("Bearer test-access-token");
    expect(getAccessTokenSilently).toHaveBeenCalledWith({
      authorizationParams: { audience: "https://stitch-api.local" },
    });
    expect(getAccessTokenSilently.mock.invocationCallOrder[0]).toBeLessThan(
      fetchSpy.mock.invocationCallOrder[0],
    );
  });

  it("polls /status/{job_id} on refresh and renders the completed result", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockResponse(202, RUNNING_RECORD))
      .mockResolvedValueOnce(mockResponse(200, SUCCEEDED_RECORD));

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => {
      expect(screen.getByText("running")).toBeInTheDocument();
    });

    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Match groups" }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText("2 groups")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Match group 1" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Resource 101")).toBeInTheDocument();
    expect(screen.getByText("Resource 205")).toBeInTheDocument();

    // The status poll hits /status/{job_id} (unauthenticated GET).
    const [statusUrl] = fetchSpy.mock.calls[1];
    expect(statusUrl).toMatch(/\/status\/job-123$/);
  });

  it("surfaces a failed run", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockResponse(202, RUNNING_RECORD))
      .mockResolvedValueOnce(
        mockResponse(200, {
          ...RUNNING_RECORD,
          state: "failed",
          finished_at: "2026-01-01T00:00:05Z",
          error: "GET /oil-gas-fields/ failed with status 500: boom",
        }),
      );

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => screen.getByText("running"));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText("Run failed.")).toBeInTheDocument();
    });
    expect(screen.getByText("failed")).toBeInTheDocument();
  });
});
