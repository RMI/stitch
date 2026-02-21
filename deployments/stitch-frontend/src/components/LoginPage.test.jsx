import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults } from "../test/utils";
import LoginPage from "./LoginPage";

describe("LoginPage", () => {
  it("renders app name and description", () => {
    render(<LoginPage />);

    expect(screen.getByText("Stitch")).toBeInTheDocument();
    expect(
      screen.getByText("Oil & Gas Asset Data Platform"),
    ).toBeInTheDocument();
  });

  it("calls loginWithRedirect on button click", async () => {
    const loginWithRedirect = vi.fn();
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      loginWithRedirect,
    });

    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(
      screen.getByRole("button", { name: /log in to continue/i }),
    );

    expect(loginWithRedirect).toHaveBeenCalled();
  });
});
