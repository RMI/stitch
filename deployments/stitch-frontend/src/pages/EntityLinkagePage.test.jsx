import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EntityLinkagePage from "./EntityLinkagePage";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

describe("EntityLinkagePage", () => {
  beforeEach(() => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      getAccessTokenSilently: vi.fn().mockResolvedValue("test-access-token"),
    });
  });

  it("renders match groups as visually separated groups", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          initiated_by: "Test User",
          apply_merges: false,
          pages_fetched: 1,
          total_records_fetched: 4,
          duplicate_name_candidate_count: 4,
          detail_records_fetched: 4,
          match_groups: [
            [101, 102],
            [203, 204, 205],
          ],
          merge_results: [],
        }),
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Match groups" }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("2 groups")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Match group 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Match group 2" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Resource 101")).toBeInTheDocument();
    expect(screen.getByText("Resource 205")).toBeInTheDocument();
  });
});
