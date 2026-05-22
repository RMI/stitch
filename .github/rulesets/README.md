# GitHub Rulesets

These json files represent [GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

Each is created by exporting an existing ruleset in effect in this repo.

# Export

To create a ruleset file from an existing ruleset (usually created through the web UI):

- In Repo Settings, on the sidebar, go to "Rules" -> "Rulesets".
- Find the ruleset you want to export.
- In the "..." (three dots) menu, "Export Ruleset".

# Import

NOTE: If you are updating an existing ruleset, see "Update" below.

To import a new ruleset (from a file) into the repo's settings:

- In Repo Settings, on the sidebar, go to "Rules" -> "Rulesets".
- Click the green "New Ruleset" -> "Import a ruleset".
- Navigate to a JSON file (on your local machine) that defines the ruleset you want.
- Scroll to bottom of page and **"Create"**

# Update

If you want to alter an existing ruleset (such as adding required checks, see [PR#189](https://github.com/RMI/pbtar/pull/189)):

- In Repo Settings, on the sidebar, go to "Rules" -> "Rulesets".
- Find the ruleset you want to update.
- Click on the ruleset name (not three-dots) to see rulest definition in the WebUI.
  - Rename the ruleset (suggestion `rule-name` -> `rule-name-old`)
  - Set "Enforcement Status" to "Disabled"
  - Scroll to bottom of page and **"Save Changes"**
- Return to "Rulesets" main page, and import the updated definiton (see above, "Import").
- Repeat if changing multiple rulesets
- _(Testing):_
  - Trigger an empty commit: `git commit -m "Trigger CI" --allow-empty` and push to trigger checking action
  - The action **should fail**.
  - You should see in the `diff`:
    - You will also see the `*_old` actions as having no comparisons.
  - If there are no differences in the ruleset you updated, then it has imported as expected, and you can delete the `*_old` ruleset in the Repo settings.
    - "Rulesets" -> "`*_old`" -> "..." \_. "Delete ruleset".
  - Trigger a new empty commit and push.
  - There should be no diffs, and actions run cleanly with new rulesets in effect.
