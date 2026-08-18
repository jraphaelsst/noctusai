# `swagger.v3.json` — provenance

| Field | Value |
|---|---|
| Source URL | `https://developer.atlassian.com/cloud/trello/swagger.v3.json` |
| Fetch date | 2026-08-18 |
| OpenAPI version | `3.0.0` |
| API title / version | `Trello REST API` / `0.0.1` |
| File size | 261 671 bytes |
| sha256 | `b50fca38c5ea62025f9778482f89f11ae3da0dd983d31ba49401c4422e450b19` |
| Operation count | 261 |
| Schema count (`components.schemas`) | 63 |

## Why this file is here (not fetched at call-time)

This connector's primary job (per `mcp/trello/README.md`) is to be a
**queryable map of Trello's product surface** for designing the
lead-card-hub organ (`project-history/roadmaps/lead-card-hub-2026-08.md`).
Vendoring the spec means the `trello.contract.*` tools work with **zero
network calls and zero credentials, forever** — a design session does not
depend on Atlassian's docs host being up, and a spec refresh is a
deliberate, reviewable diff instead of a tool silently changing its
answers between calls.

## Per-resource operation counts (verified against this exact file)

Root path segment → operation count (sums to 261):

| resource | count |
|---|---:|
| members | 45 |
| cards | 42 |
| boards | 41 |
| organizations | 26 |
| enterprises | 21 |
| actions | 16 |
| checklists | 12 |
| lists | 11 |
| notifications | 11 |
| customFields | 8 |
| tokens | 8 |
| labels | 5 |
| plugins | 5 |
| webhooks | 5 |
| search | 2 |
| applications | 1 |
| batch | 1 |
| emoji | 1 |

`mcp/trello/tests/test_contract_spec_facts.py` asserts every count above
directly against the vendored file, plus the `Card.badges` field set and
the `PUT /cards/{id}` writable parameter list — so a future spec refresh
that changes any of these facts fails the suite loudly instead of the
`trello.contract.*` tools silently answering something new.

## Refreshing this file

1. Re-fetch `https://developer.atlassian.com/cloud/trello/swagger.v3.json`.
2. Overwrite `mcp/trello/contract/swagger.v3.json`.
3. Re-run `sha256sum mcp/trello/contract/swagger.v3.json`, update the table
   above (source URL, fetch date, size, sha256).
4. Run `pytest mcp/trello/tests/test_contract_spec_facts.py -q` — any
   assertion that fails names exactly which fact moved; update the
   assertion (and the per-resource table above) to match the new spec,
   deliberately, rather than loosening it.
5. Re-run the full `mcp/trello` suite.
