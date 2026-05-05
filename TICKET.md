# Story: Search and Browse Usability

## Story

As an SME reviewer, I need resource browsing to feel like exploration instead of manual API fetching so I can quickly find fields of interest without working like an API client.

## Goal

Improve the main resource browser so it behaves like a normal searchable list:

- load results automatically on page entry
- support free-text search using the backend `q` parameter
- remove the explicit fetch-first interaction from the primary browse flow
- keep pagination, sorting, and filters working coherently together

## Acceptance Criteria

- The main resource list loads automatically when the user lands on the page.
- Users can enter free-text search from the main browser UI.
- Free-text search is backed by the existing backend `q` capability rather than a separate client-side search implementation.
- Changing search text resets pagination to page 1.
- Changing filters resets pagination to page 1.
- Changing sort resets pagination to page 1.
- Pagination continues to work with active search, filters, and sorting.
- The primary resource browser no longer requires clicking a Fetch button before results appear.
- Loading and error states remain clear and consistent in the updated flow.
- Frontend test coverage is added or updated for the new browse behavior.

## Non-Goals

- Designing or implementing advanced search syntax.
- Adding saved searches, recent searches, or search suggestions.
- Reworking backend query semantics beyond passing through the existing `q` parameter.
- Solving the broader filter-option problem where options are derived only from the current page of results.
- Refactoring the standalone single-resource fetch panel as part of this ticket.
- General frontend architecture cleanup outside the main browse flow.
