## What

`release_steward._record_failing_items` (guardian-protected, not authored here) writes a `deny` gate event for every delivery-contract item with `ok` false. Item 5 `scoped_green` with a still-running CI run is `pending_ci` by the tool's own contract ("a still-running run is item 5 PENDING, never a resync"), yet it is recorded as a deny with class `deliverable:scoped_green:ci-running:-https://github.com/.../actions/runs/<id>-pending`: 77 denies / 5 sessions in 14d (2026-11-16..19). Pollers re-reading a pending run inflate the recurrence count and the class key even embeds the run URL (a volatile token).

## Proposed fix (steward-owned file)

In `_record_failing_items`, skip items whose verdict is pending (or record `warn`, not `deny`) and keep the run id out of the class key. Same for `migrations_free: not measurable: no composed tree` (27 denies on two branches): it is a derivative of `merge_buildable` and should not be a separate denied class.

## Why it is not blocking the backlog work

`refusal-class-policy.json` declares the `deliverable:` prefix intended (per-branch resync refusals), so the recurrence andon does not count these. The proposal removes the noise at the source and makes `gate_alignment walls` honest for the deliverable gate.

Owner: release-steward / guardian authorship fence (check_guardian_tool_authorship); route through the tooling branch steward.