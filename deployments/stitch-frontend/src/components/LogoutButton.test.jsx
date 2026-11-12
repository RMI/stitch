import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import { auth0TestDefaults } from "../test/utils";
import { LogoutButton } from "./LogoutButton";

describe("LogoutButton", () => {
  it("renders when authenticated", () => {
    render(<LogoutButton />);
    expect(
      screen.getByRole("button", { name: /log out/i }),
    ).toBeInTheDocument();
  });

  it("does not render when not authenticated", () => {
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      isAuthenticated: false,
    });

    const { container } = render(<LogoutButton />);
    expect(container).toBeEmptyDOMElement();
  });

  it("calls logout with returnTo on click", async () => {
    const logout = vi.fn();
    vi.mocked(useAuth0).mockReturnValue({ ...auth0TestDefaults, logout });

    const user = userEvent.setup();
    render(<LogoutButton />);
    await user.click(screen.getByRole("button", { name: /log out/i }));

    expect(logout).toHaveBeenCalledWith({
      logoutParams: { returnTo: window.location.origin },
    });
  });
});
