import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setConfigForTests } from "../config/env";
import { renderWithQueryClient } from "../test/utils";

function createMockConfig() {
  return {
    appEnv: "local",
    apiBaseUrl: "http://localhost:8000/api/v1",
    entityLinkageBaseUrl: "http://localhost:8001/api/v1",
    auth0: {
      domain: "example.auth0.com",
      clientId: "client-id",
      audience: "https://stitch-api.local",
    },
    build: {
      appVersion: "0.0.0",
      buildId: "local-build",
      gitSha: "abcdef123456",
      nodeVersion: "v20.0.0",
      viteVersion: "^7.2.4",
      buildTime: "2026-04-06T12:00:00Z",
    },
  };
}

vi.mock("./ColophonPanel", () => ({
  default: ({ diagnosticsOpen }) => (
    <div data-testid="colophon-panel">
      Diagnostics open: {String(diagnosticsOpen)}
    </div>
  ),
}));

describe("EnvironmentBanner", () => {
  let mockConfig;

  beforeEach(() => {
    mockConfig = createMockConfig();
    setConfigForTests(mockConfig);
  });

  it("renders for a non-production environment", async () => {
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    renderWithQueryClient(<EnvironmentBanner />);

    expect(screen.getByText("LOCAL Environment")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Show diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("colophon-panel")).not.toBeInTheDocument();
  });

  it("hides entirely for production", async () => {
    setConfigForTests({
      ...createMockConfig(),
      appEnv: "production",
    });
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    const { container } = renderWithQueryClient(<EnvironmentBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders for dress-rehearsal", async () => {
    setConfigForTests({
      ...createMockConfig(),
      appEnv: "dress-rehearsal",
    });
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    renderWithQueryClient(<EnvironmentBanner />);

    expect(screen.getByText("DRESS-REHEARSAL Environment")).toBeInTheDocument();
  });

  it("toggles the diagnostics panel open and closed", async () => {
    const user = userEvent.setup();
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    renderWithQueryClient(<EnvironmentBanner />);

    const toggle = screen.getByRole("button", { name: "Show diagnostics" });

    await user.click(toggle);
    expect(
      screen.getByRole("button", { name: "Hide diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("colophon-panel")).toHaveTextContent(
      "Diagnostics open: true",
    );

    await user.click(screen.getByRole("button", { name: "Hide diagnostics" }));
    expect(
      screen.getByRole("button", { name: "Show diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("colophon-panel")).not.toBeInTheDocument();
  });
});
