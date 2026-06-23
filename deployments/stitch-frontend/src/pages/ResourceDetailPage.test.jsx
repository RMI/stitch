import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import ResourceDetailPage from "./ResourceDetailPage";
import { useResourceDetail, useSourceDetail } from "../hooks/useResources";
import * as apiModule from "../queries/api";
import * as jobsModule from "../queries/jobs";

vi.mock("../hooks/useResources");

let mockedRouteId = "1";
const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: mockedRouteId }),
    useNavigate: () => mockNavigate,
  };
});

const mockDetailView = {
  id: 1,
  data: {
    name: "Burgan Field",
    country: "Kuwait",
    state_province: "Kuwait",
    region: "Middle East",
    basin: "Arabian",
    latitude: 29.05,
    longitude: 47.95,
    location_type: "Onshore",
    name_local: null,
    owners: [{ name: "Kuwait Oil Company", stake: 100 }],
    operators: [{ name: "Kuwait Oil Company", stake: 100 }],
    field_status: "Producing",
    production_conventionality: "Conventional",
    primary_hydrocarbon_group: "Oil",
    reservoir_formation: "Burgan",
    discovery_year: 1938,
    production_start_year: 1946,
    fid_year: null,
  },
  provenance: {},
  source_data: [
    {
      id: 11,
      source: "gem",
      name: "Burgan Source",
      country: "Kuwait",
    },
  ],
};

const defaultSourceDetailHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
};

const defaultHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  mockedRouteId = "1";
  mockNavigate.mockReset();
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  vi.mocked(useResourceDetail).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
  vi.mocked(useSourceDetail).mockReturnValue(defaultSourceDetailHookReturn);
  // Default: no prior jobs for the current resource/field (the panel loads
  // these on mount). Individual tests override to exercise "Show suggestion".
  vi.spyOn(jobsModule, "listJobs").mockResolvedValue([]);
  vi.stubGlobal("crypto", {
    randomUUID: () => "persist-uuid-123",
  });
});

describe("ResourceDetailPage", () => {
  it("shows an invalid ID message for a non-numeric route param", () => {
    mockedRouteId = "not-a-number";

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/invalid resource id/i)).toBeInTheDocument();
  });

  it("shows a loading indicator while fetching", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      isLoading: true,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error message on fetch failure", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      isError: true,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/failed to load resource/i)).toBeInTheDocument();
  });

  it("renders the resource name as the page heading", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: "Burgan Field", level: 1 }),
    ).toBeInTheDocument();
  });

  it("renders the Identity and Location section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /identity and location/i }),
    ).toBeInTheDocument();
  });

  it("renders identity fields with their values", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Country").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Kuwait").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Region").length).toBeGreaterThan(0);
    expect(screen.getByText("Middle East")).toBeInTheDocument();
  });

  it("renders an em dash for null identity fields", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText("Local Name")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders the Organizations section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /organizations/i }),
    ).toBeInTheDocument();
  });

  it("renders owner and operator names", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Kuwait Oil Company").length).toBeGreaterThan(0);
  });

  it("renders the Production and Geology section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /production and geology/i }),
    ).toBeInTheDocument();
  });

  it("renders production fields with their values", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Field Status").length).toBeGreaterThan(0);
    expect(screen.getByText("Producing")).toBeInTheDocument();
    expect(screen.getAllByText("Discovery Year").length).toBeGreaterThan(0);
    expect(screen.getByText("1938")).toBeInTheDocument();
  });

  it("renders the Data Source Mix section", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /data source mix/i }),
    ).toBeInTheDocument();
  });

  it("renders the AI Suggestion section", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByRole("heading", { name: /ai suggestion/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /generate suggestion/i }),
    ).toBeInTheDocument();
  });

  it("renders a Sources section with a row per attached source", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByRole("heading", { name: /^sources$/i, level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^view$/i })).toBeInTheDocument();
    expect(screen.getAllByText("Burgan Source").length).toBeGreaterThan(0);
  });

  it("exposes disclosure accessibility attributes on the source row toggle", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);

    const toggle = screen.getByRole("button", { name: /^view$/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();

    await user.click(toggle);

    expect(screen.getByRole("button", { name: /^hide$/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(document.getElementById(panelId)).toBeTruthy();
  });

  it("shows formatted producer and observed-at in the compact row once the source detail loads", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "gem",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-seed@0.1.0",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: "abc",
          run_id: "run-1",
          payload: { name: "Burgan Source" },
        },
      },
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByText(/imported by stitch-seed@0\.1\.0/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/may 13, 2026/i)).toBeInTheDocument();
    expect(screen.queryByText(/"name": "Burgan Source"/)).toBeNull();
  });

  it("reveals the raw payload only after the Technical import record disclosure is opened", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "gem",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-seed@0.1.0",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: "abc",
          run_id: "run-1",
          payload: { name: "Burgan Source" },
        },
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("button", { name: /^view$/i }));

    const techToggle = screen.getByRole("button", {
      name: /technical import record/i,
    });
    expect(techToggle).toBeInTheDocument();
    expect(screen.queryByText(/"name": "Burgan Source"/)).toBeNull();

    await user.click(techToggle);

    expect(screen.getByText(/"name": "Burgan Source"/)).toBeInTheDocument();
    expect(screen.getByText("abc")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });

  it("generates and renders an AI suggestion preview", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [
          {
            url: "https://example.com/daqing",
            title: "Daqing citation",
          },
        ],
        query_succeeded: true,
        model: "test-model",
        rationale: "Public sources place Daqing in the Songliao Basin.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(
      screen.getByText("Public sources place Daqing in the Songliao Basin."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Daqing citation" }),
    ).toHaveAttribute("href", "https://example.com/daqing");
  });

  it("polls the status endpoint until the job finishes, then renders the result", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "running",
      result: null,
    });
    vi.spyOn(jobsModule, "getJobStatus").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByText("Songliao", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(jobsModule.getJobStatus).toHaveBeenCalled();
  });

  it("renders the failure when the job fails", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "failed",
      result: null,
      error: "field already populated",
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByText("field already populated"),
    ).toBeInTheDocument();
  });

  it("passes force=true when Re-run is checked", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const startSpy = vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("checkbox", { name: /re-run/i }));
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    await screen.findByText("Songliao");
    expect(startSpy).toHaveBeenCalledWith(
      expect.stringContaining("oil-gas-fields"),
      expect.objectContaining({ resource_id: 1, field: "basin", force: true }),
      expect.anything(),
    );
  });

  it("offers 'Show suggestion' for a pre-existing result and reveals it without re-running", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "listJobs").mockResolvedValue([
      {
        job_id: "prior-1",
        state: "succeeded",
        started_at: "2026-05-13T12:00:00Z",
        params: { resource_id: 1, field: "basin" },
        result: {
          resource_id: 1,
          field: "basin",
          value: "Songliao",
          citations: [],
          query_succeeded: true,
          model: "test-model",
          rationale: "From a prior run.",
          observed_at: "2026-05-13T12:00:00Z",
          foundry_request: {},
          foundry_response: {},
        },
      },
    ]);
    const startSpy = vi.spyOn(jobsModule, "startJob");
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);

    const showButton = await screen.findByRole("button", {
      name: /show suggestion/i,
    });
    await user.click(showButton);

    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(startSpy).not.toHaveBeenCalled();
  });

  it("renders a no-answer suggestion state without treating it as an error", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: null,
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "I could not find a grounded public source for this field.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByText(/no grounded suggestion was returned/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "I could not find a grounded public source for this field.",
      ),
    ).toBeInTheDocument();
  });

  it("renders Add to resource only when the suggestion has a value", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByRole("button", { name: /add to resource/i }),
    ).toBeInTheDocument();
  });

  it("creates an LLM-backed resource, then creates a merge candidate, and leaves the user on the page", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [
          { url: "https://example.com/source", title: "Example Source" },
        ],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: { request: true },
        foundry_response: { response: true },
      },
    });
    const createResourceSpy = vi
      .spyOn(apiModule, "createResource")
      .mockResolvedValue({ id: 123 });
    const createMergeCandidateSpy = vi
      .spyOn(apiModule, "createMergeCandidate")
      .mockResolvedValue({ id: 88, resource_ids: [1, 123] });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(createResourceSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBaseUrl: "http://localhost:8000/api/v1",
        stitchLlmBaseUrl: "http://localhost:8002/api/v1",
      }),
      {
        id: null,
        repointed_to: null,
        constituents: [],
        provenance: {},
        view: null,
        source_data: [
          {
            id: null,
            source: "llm",
            name: null,
            country: null,
            basin: "Songliao",
            source_record: {
              record_id: "persist-uuid-123",
              run_id: null,
              observed_at: "2026-05-13T12:00:00Z",
              producer: "stitch-frontend",
              payload: {
                resource_id: 1,
                field: "basin",
                suggested_value: "Songliao",
                rationale: "Supported.",
                citations: [
                  {
                    url: "https://example.com/source",
                    title: "Example Source",
                  },
                ],
                model: "test-model",
                foundry_request: { request: true },
                foundry_response: { response: true },
                persist_intent_id: "persist-uuid-123",
              },
            },
          },
        ],
      },
      expect.any(Function),
      "oil-gas-fields",
    );
    expect(createMergeCandidateSpy).toHaveBeenCalledWith(
      expect.any(Object),
      [1, 123],
      expect.any(Function),
      "oil-gas-fields",
    );
    expect(
      await screen.findByText(
        "Suggestion saved and queued for later merge review.",
      ),
    ).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalledWith(
      "/merge-candidate-review?candidate=88",
    );
  });

  it("renders structured create-resource validation errors instead of object coercions", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    vi.spyOn(apiModule, "createResource").mockRejectedValue(
      new Error(
        JSON.stringify(
          [
            {
              loc: ["body", "source_data", 0, "llm", "name"],
              msg: "Field required",
            },
            {
              loc: ["body", "source_data", 0, "llm", "country"],
              msg: "Field required",
            },
          ],
          null,
          2,
        ),
      ),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(await screen.findByText(/Field required/)).toBeInTheDocument();
    expect(
      screen.queryByText("[object Object],[object Object]"),
    ).not.toBeInTheDocument();
  });

  it("shows partial-failure messaging when merge candidate creation fails after resource creation", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    vi.spyOn(apiModule, "createResource").mockResolvedValue({ id: 123 });
    const createMergeCandidateSpy = vi
      .spyOn(apiModule, "createMergeCandidate")
      .mockRejectedValue(new Error("merge failed"));
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(createMergeCandidateSpy).toHaveBeenCalled();
    expect(
      await screen.findByText(
        "Suggestion saved as resource 123, but the merge draft was not created.",
      ),
    ).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("does not attempt merge-candidate creation when resource creation fails", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    vi.spyOn(apiModule, "createResource").mockRejectedValue(
      new Error("create failed"),
    );
    const createMergeCandidateSpy = vi.spyOn(apiModule, "createMergeCandidate");
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(createMergeCandidateSpy).not.toHaveBeenCalled();
    expect(await screen.findByText("create failed")).toBeInTheDocument();
  });

  it("disables resubmission after a successful persist for the current suggestion", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      job_id: "job-1",
      state: "succeeded",
      result: {
        resource_id: 1,
        field: "basin",
        value: "Songliao",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      },
    });
    vi.spyOn(apiModule, "createResource").mockResolvedValue({ id: 123 });
    vi.spyOn(apiModule, "createMergeCandidate").mockResolvedValue({
      id: 88,
      resource_ids: [1, 123],
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(
      await screen.findByRole("button", { name: /added to resource/i }),
    ).toBeDisabled();
  });
});
