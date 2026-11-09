# Contract — council ledger (v1.1, 2026-11-09)

> The one row schema that the ledger tool (`noctus.dev.council_ledger`) and the
> `noc-council` skill build to. Owner decisions D6–D17 are in the live spec:
> https://claude.ai/artifact/13Bt8tb93ruTZovtoeCgxV. Change this file first, then its consumers.
> Shape rule: `KB § PATTERNS/architect/measurement-by-design.md`. Entities are rows, state changes are
> append-only events, closed sets are enums (never free text), and each metric has exactly one derivation.

## 1 · Records

All ids are UUIDv4 strings. Every timestamp is ISO-8601 UTC. Every row carries
`recorded_by` (Claude session id or `owner`) and `recorded_at`. The fields marked † are nullable.

### `session` — one council convened on one subject
| field | type | notes |
|---|---|---|
| `session_id` | uuid | |
| `stage` | enum `stage` | §2 |
| `subject_kind` | enum `subject_kind` | §2 |
| `subject_ref` | text | e.g. a branch, an artifact URL, an `eval_run` id (noc-1's agent-creator link), a doc section |
| `trigger` | enum `trigger` | why the council met (§2) |
| `mode` | enum `mode` | `subagents` now; `api` once in-app; `single_chat` for the labelled-not-independent fallback |
| `seats` | text[] | `lens:<lens>` or `advisor:<agent-name>`, per the stage map in `noc-council` |
| `brief_sha256` | text | hash of the brief every councillor got (without the author's recommendation) |
| `project` † | text | e.g. `assistant-chatbot` |

### `objection` — one councillor's point (written before anyone sees the others)
| field | type | notes |
|---|---|---|
| `objection_id` | uuid | |
| `session_id` | uuid | FK session |
| `seat` | text | as in `seats` |
| `anon_label` | text | `A`..`Z`, then `AA`.. ; ASSIGNED BY THE TOOL (random, unique per session); the caller cannot pass one; this is what the chair sees |
| `severity` | enum `severity` | §2 |
| `claim` | text | the objection in ≤ 3 sentences |
| `model` | text | e.g. `sonnet`, `opus` |
| `tokens` † | int | from the subagent usage, when reported |

### `verdict` — the chair's synthesis (one per session)
| field | type | notes |
|---|---|---|
| `session_id` | uuid | |
| `chair_kind` | enum `chair_kind` | §2 |
| `decision` | text | |
| `biggest_risk` | text | |
| `first_step` | text | |
| `dispositions` | `[{objection_id, disposition: enum disposition, reason}]` | every objection gets one |
| `tokens` † | int | |

### `event` — append-only, later state changes
| field | type | notes |
|---|---|---|
| `event_id` | uuid | |
| `event_kind` | enum `event_kind` | `ratified` · `overruled` (the tech-lead or owner on a verdict, D14) · `outcome` |
| `session_id` | uuid | |
| `objection_id` † | uuid | required when `event_kind=outcome` |
| `outcome` † | enum `outcome` | required when `event_kind=outcome` |
| `evidence_kind` † | enum `evidence_kind` | required when `event_kind=outcome` |
| `evidence_ref` † | text | commit sha, incident id, eval run id, … |
| `note` † | text | |

## 2 · Enums (closed; adding a value = a contract bump)
- `stage`: `idealize` · `phase0` · `verify_seed` · `mockup` · `contract` · `build` · `wire` · `test_review` · `security_pass` · `evaluate` · `ship` · `go_live` · `iterate` · `owner_question`
- `subject_kind`: `plan` · `decision` · `agent_definition` · `skill` · `product` · `contract` · `refine` · `eval_run` · `question`
- `trigger`: `stage_map` (every stage, this run, D13) · `new_product` · `irreversible` · `trust_boundary` · `prod_exposure` · `money_legal_lgpd` · `seed_fanout` · `large_estimate` · `unrebutted_objection`
- `mode`: `subagents` · `api` · `single_chat`
- `severity`: `blocker` · `major` · `minor` · `note`
- `chair_kind`: `chair_agent` · `tech_lead` · `api_chair`
- `disposition`: `accepted` · `rejected` · `deferred`
- `event_kind`: `ratified` · `overruled` · `outcome`
- `outcome`: `vindicated` (the objection proved right) · `refuted` (proved wrong) · `untested`
- `evidence_kind`: `commit` · `revert` · `incident` · `owner_reversal` · `eval_run` · `test` · `review`

## 3 · Metrics (one derivation each, per seat; computed by `council_ledger action=report`)
- **hit_rate** = vindicated ÷ (vindicated + refuted), counting only each objection's latest `outcome`.
- **unique_hit_rate** = vindicated objections whose claim no other seat in the same session raised (the chair marks this in `dispositions.reason`: the reason is `unique` alone or `unique` followed by one of `: ; , - —` and free text, case-insensitive; anything else, e.g. `shared with A`, is not unique) ÷ vindicated.
- **false_alarm_rate** = refuted ÷ objections with an outcome (any outcome, including `untested`, counts in the denominator).
- **acceptance_rate** = accepted ÷ dispositions.
- **cost_per_hit** = Σ tokens ÷ vindicated.
- **retune signal**: a seat with ≥ 10 resolved objections on a stage whose hit_rate is under 0.2 → propose demoting M→O on the stage map; one over 0.6 that is O → propose promoting. The owner ratifies; the skill never auto-edits the map.

## 4 · Storage (D9, D12; ledger-first, owner decision 2026-11-09)
- **ndjson in git is the SOURCE OF TRUTH**: `project-history/council/<YYYY-MM>/<session_id>.ndjson`. One file per session, so parallel branches never conflict. Each line is `{"record": "session|objection|verdict|event", ...fields}`. Append-only: a correction is a new `event`, never an edit.
- **No DB leg for now.** A DB mirror and any UI are deferred (owner decision pending). The parked design (agents migration 073, insert-only tables, sync action and pre-push id check) lives on branch `feat/council-db-parked`.
- **Gate**: a pre-commit keeper validates every staged ledger file against this schema and that a staged diff only appends at EOF (offline).

## 5 · Neutral recorder (v1.1, owner decision 2026-11-09)
- `anon_label` is assigned by the tool on `record_objection`; a caller-supplied label is refused. The result is only `{objection_id, status:"submitted"}`: never the label, never the seat mapping.
- `blind_view(session_id)` returns each objection as `{anon_label, severity, claim}` only (no seat, no model, no id) for the chair. `record_verdict` accepts dispositions keyed by `anon_label` and translates them to `objection_id`.
- Seats are revealed only after a verdict row exists: `full_view` refuses before it; `status` omits seats before it; `report` aggregates only sessions that have a verdict.

## 6 · Validation rules (as built)
- `session_id` is a UUIDv4; `seats` has at least one entry and no repeats; one `seat` entry per objection must be one of the session's seats.
- `dispositions` is a JSONB array of exactly `{objection_id, disposition, reason}` objects; the verdict disposes every objection exactly once and no unknown one; a session has one verdict.
- No objection may be recorded after the verdict. `ratified` and `overruled` events require a verdict first and must NOT carry `objection_id`, `outcome` or `evidence_kind` (outcome fields are only for `event_kind=outcome`).
- `recorded_at` is supplied by the writer (the tool stamps now when omitted).

## Changelog
- v1.1 (2026-11-09): ledger-first (ndjson is the source of truth; DB leg, sync action and pre-push check parked on `feat/council-db-parked`), neutral recorder (tool-assigned `anon_label`, `blind_view`, seat reveal after verdict), false_alarm_rate denominator and `unique` grammar stated, as-built validation rules recorded.
- v1 (2026-11-09): initial.
