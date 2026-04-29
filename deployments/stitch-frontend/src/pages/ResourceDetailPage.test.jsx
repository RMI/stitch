import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import ResourceDetailPage from "./ResourceDetailPage";
import { useResourceDetail } from "../hooks/useResources";
import * as apiModule from "../queries/api";

vi.mock("../hooks/useResources");

let mockedRouteId = "1";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: mockedRouteId }),
    useNavigate: () => vi.fn(),
  };
});

// Fixture with the same shape as the real API / mock data response.
// Tests assert against structure and labels — not specific values — so this
// works regardless of which data source (real API or mock) is active in the app.
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
  source_data: [],
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
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  vi.mocked(useResourceDetail).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
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
    expect(screen.getByText("Country")).toBeInTheDocument();
    // country and state_province both equal "Kuwait" in the fixture, so two matches are expected
    expect(screen.getAllByText("Kuwait").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Region")).toBeInTheDocument();
    expect(screen.getByText("Middle East")).toBeInTheDocument();
  });

  it("renders an em dash for null identity fields", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    // name_local is null in the fixture
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

  it("generates and renders an AI suggestion preview", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
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
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Daqing citation" }),
    ).toHaveAttribute("href", "https://example.com/daqing");
  });
});
