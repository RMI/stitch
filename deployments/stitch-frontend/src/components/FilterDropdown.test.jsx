import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FilterDropdown from "./FilterDropdown";

const COUNTRY_OPTIONS = [
  // Real country names come from Intl.DisplayNames, which uses a curly
  // apostrophe (U+2019) here.
  { value: "CIV", label: "Côte d\u2019Ivoire" },
  { value: "CUW", label: "Curaçao" },
  { value: "NGA", label: "Nigeria" },
  { value: "NOR", label: "Norway" },
  { value: "SWE", label: "Sweden" },
];

function renderDropdown(props = {}) {
  const onChange = vi.fn();
  render(
    <FilterDropdown
      label="Country"
      options={COUNTRY_OPTIONS}
      selected={[]}
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange };
}

async function open(user) {
  await user.click(screen.getByRole("button", { name: /country/i }));
}

function visibleOptionLabels() {
  return within(screen.getByRole("listbox"))
    .getAllByRole("checkbox")
    .map((checkbox) => checkbox.closest("label").textContent.trim());
}

describe("FilterDropdown", () => {
  it("has no search box unless the filter is searchable", async () => {
    const user = userEvent.setup();
    renderDropdown();
    await open(user);

    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(visibleOptionLabels()).toHaveLength(COUNTRY_OPTIONS.length);
  });

  describe("when searchable", () => {
    it("shows a focused search box at the top of the open dropdown", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      const search = screen.getByRole("searchbox", { name: "Search Country" });
      expect(search).toHaveAttribute("placeholder", "Search Country");
      expect(search).toHaveFocus();
    });

    it("filters the options by case-insensitive substring of the label", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      await user.type(screen.getByRole("searchbox"), "NOR");
      expect(visibleOptionLabels()).toEqual(["Norway"]);

      await user.clear(screen.getByRole("searchbox"));
      await user.type(screen.getByRole("searchbox"), "er");
      expect(visibleOptionLabels()).toEqual(["Nigeria"]);
    });

    it("matches the displayed label, not the hidden value", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      // Stored codes whose letters don't appear in the country name: users
      // only ever see the name, so the code must not match.
      await user.type(screen.getByRole("searchbox"), "civ");
      expect(screen.getByText("No matches")).toBeInTheDocument();
      await user.clear(screen.getByRole("searchbox"));
      await user.type(screen.getByRole("searchbox"), "nga");
      expect(screen.getByText("No matches")).toBeInTheDocument();
    });

    it("ignores accents in either the search text or the label", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      await user.type(screen.getByRole("searchbox"), "cote");
      expect(visibleOptionLabels()).toEqual(["Côte d\u2019Ivoire"]);

      await user.clear(screen.getByRole("searchbox"));
      await user.type(screen.getByRole("searchbox"), "CURAÇAO");
      expect(visibleOptionLabels()).toEqual(["Curaçao"]);
    });

    it("treats curly and straight apostrophes as the same", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      // What a keyboard types: a straight apostrophe.
      await user.type(screen.getByRole("searchbox"), "cote d'ivoire");
      expect(visibleOptionLabels()).toEqual(["Côte d\u2019Ivoire"]);
    });

    it('shows "No matches" when nothing matches', async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      await user.type(screen.getByRole("searchbox"), "atlantis");

      expect(screen.getByText("No matches")).toBeInTheDocument();
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("keeps a hidden ticked option selected while toggling a visible one", async () => {
      const user = userEvent.setup();
      const { onChange } = renderDropdown({
        searchable: true,
        selected: ["SWE"],
      });
      await open(user);

      await user.type(screen.getByRole("searchbox"), "nor");
      expect(onChange).not.toHaveBeenCalled();

      await user.click(screen.getByRole("checkbox", { name: "Norway" }));
      expect(onChange).toHaveBeenCalledWith(["SWE", "NOR"]);
    });

    it("clears the search text when the dropdown is closed and reopened", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);
      await user.type(screen.getByRole("searchbox"), "nor");

      await open(user); // close
      await open(user); // reopen

      expect(screen.getByRole("searchbox")).toHaveValue("");
      expect(visibleOptionLabels()).toHaveLength(COUNTRY_OPTIONS.length);
    });

    it("closes the dropdown when Escape is pressed in the search box", async () => {
      const user = userEvent.setup();
      renderDropdown({ searchable: true });
      await open(user);

      await user.type(screen.getByRole("searchbox"), "nor{Escape}");

      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
      // Focus goes back to the dropdown's button, not lost with the panel.
      expect(screen.getByRole("button", { name: /country/i })).toHaveFocus();
    });
  });
});
