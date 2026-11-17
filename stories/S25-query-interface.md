# S25 — Natural Language Query Interface
**Epic**: E6 Frontend | **Priority**: P0 | **Assigned**: frontend-dev  
**Depends on**: S24, S06

## Description
Implement the main query input interface: a prominent text area for natural language queries, example query chips for discoverability, submission handling, and navigation to the analysis result page.

## Acceptance Criteria
- [ ] `frontend/components/query/QueryInput.tsx`
  - Textarea: auto-grows to max 4 lines, placeholder text
  - Submit button with loading spinner during API call
  - Keyboard shortcut: `Ctrl+Enter` submits
  - Character counter (max 2000)
  - Error display if API call fails
- [ ] `frontend/components/query/ExampleQueries.tsx`
  - 5 clickable chips that pre-fill the textarea
  - Examples: "Analyse employment trends in technology sector 2020-2024", "Compare unemployment rates across age groups 2019-2024", "What sectors had highest wage growth in Singapore post-COVID?", "Show ICT workforce growth compared to overall employment", "Analyse business registration trends by industry 2021-2024"
- [ ] On successful submit: navigate to `/dashboard/analysis/{id}`
- [ ] On submit: show toast "Analysis started — tracking in real time"
- [ ] Input disabled while loading
- [ ] Validation: empty input → shake animation + "Please enter a query"

## Technical Notes
- Use `useState` for input value and loading state
- Use TanStack Query `useMutation` for the POST call
- `useRouter().push()` for navigation after success
