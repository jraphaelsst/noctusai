# Event-Oriented Architecture (EOA) — noc's official architecture

> **Declared 2026-11-08 by the owner:** "declare it as official noc's architecture, so seed and all products behave as" event-oriented. This renames the "event-sourcing program" (P0–P5, owner decisions 2026-11-05/07) to **Event-Oriented Architecture**. Owned by architect. The program's phase state lives in `project-history/roadmaps/event-oriented-architecture-2026-11.md`.

## 1. The rule

**Every state change a noc product makes is recorded as an immutable, intent-named event, in the same transaction as the change.**

- History, reports, reactions, integrations and agents read those events.
- They never diff rows, and they never rebuild the past from today's rows.
- The seed and every product follow this through the seed primitives, never by hand.

## 2. Why "event-oriented" and not "event-driven" or "event sourcing"

"Event-oriented architecture" is **our name, not an industry standard term**. A search on 2026-11-08 found no reliable source defining it. That is why we chose it: the two standard names each say something we do not mean.

- **"Event-driven" means four different things** (Fowler, 2017):
  - event notification;
  - event-carried state transfer;
  - event sourcing;
  - CQRS.

  Saying "we are event-driven" does not say which one, and Fowler warns that confusing them makes it hard to tell which one caused a problem.
- **"Event sourcing" is one specific storage choice**: the event log, not the row, is the system of record. Specialists consistently warn against applying it to a whole system:
  - **Greg Young:** event-sourcing everything is the biggest mistake he saw in a decade; it produces an "event sourced monolith". CQRS and event sourcing "are not top-level architectures"; the system should be event-*driven*, event-*sourced* only in places.
  - **Oskar Dudycz:** event sourcing "is not a system-wide architecture concept", it is chosen per module, and a well-done CRUD beats a poorly done event-sourced one.
  - **Microsoft Azure Architecture Center:** for most systems and most parts of a system, traditional data management is sufficient. Apply event sourcing selectively, e.g. a payment ledger, not user profiles or configuration.
  - **Udi Dahan:** most teams that adopted CQRS/ES should not have; an audit log alone does not justify it.

**EOA states both halves as one rule:**
- Event-*first* everywhere: every product, every lifecycle, every change.
- Event-*sourced* only where it pays (§4).

This is how "all products behave as event-oriented" holds without building the system-wide event-sourced monolith that every source above warns against.

## 3. The building blocks (all seed-owned)

| Block | What it is | When | Seed mechanism |
|---|---|---|---|
| **E1 · Transition log** — the DEFAULT | The state row stays the truth; an immutable event is appended in the SAME locked transaction. | Every entity with a lifecycle or a history: funnel stage moves, statuses, assignments, opt-outs, sessions, approvals… | `transition_log_migration(TransitionLogConfig(...))` → `PATTERNS/backend/transition-log.md` (lands with branch `transition-log-primitive`, c585f6f3b) |
| **E2 · Event-sourced** — chosen per module | The event stream IS the system of record; state is a projection of it. | Only where §4's test passes: money, subscriptions, ledgers, clinical records. | Postgres event store `es_streams` / `es_events` / `es_checkpoints`, expected-version concurrency, idempotent replay → `PATTERNS/backend/event-store.md` (lands with `event-store-seed`, 863187f67) |
| **Projection** | A read model built from ordered events, rebuildable at any time. | Reports, dashboards, "what was true at time T", cross-module feeds. | Sync, in the writing transaction, or async with a checkpoint; drift caught by `noctus.dev.projection_reconcile` → `KB § PATTERNS/backend/projection-reconcile.md` |
| **Integration event** | A fact published to ANOTHER module or product, after commit, through an outbox. | Crossing a bounded context (agents → SW, ERP → CRM). | Outbox relay, delivered at least once. Consumers are idempotent. *Not yet a seed organ: the first cross-product consumer builds it in the seed (P5).* |

**Internal vs integration events.** A domain event is internal to its module and may change with it. An integration event is a published contract: versioned, and only as rich as the consumer needs (Verraes, Microsoft). Never expose a module's internal event table to another product.

## 3a. The event specification (normative)

EOA writes its events to open standards. It does not invent an envelope of its own.

**Normative words.** MUST, SHOULD and MAY are used as in RFC 2119.

### Envelope: CloudEvents 1.0 (CNCF)

Every noc event, in E1, E2 or an integration event, carries the CloudEvents 1.0 context attributes. Inside the database they use our column names; on the wire they use the CloudEvents names.

| CloudEvents attribute | Rule (CloudEvents 1.0) | E2 `es_events` | E1 `<agg>_events` |
|---|---|---|---|
| `id` | REQUIRED. `source`+`id` is unique per distinct event; a redelivered duplicate keeps its id. | `event_id` (UNIQUE; the idempotency key) | `id` (client event id) |
| `source` | REQUIRED URI-reference: where it happened | `metadata.source` | product/schema of the table |
| `specversion` | REQUIRED, `1.0` | implicit | implicit |
| `type` | REQUIRED; SHOULD be reverse-DNS prefixed | `event_type`, snake_case past tense; on the wire `ai.noctus.<product>.<aggregate>.<event_type>` | `event_type` |
| `subject` | OPTIONAL: the entity within the source | `stream_type`/`stream_id` | the key column(s) |
| `time` | OPTIONAL, RFC 3339 | `occurred_at` (when it happened; `recorded_at` is when it was stored) | `occurred_at` |
| `dataschema` | OPTIONAL; an incompatible change uses a NEW URI | `schema_version` (≥ 1) | `data` shape per `event_type` |
| `datacontenttype` | OPTIONAL; JSON implied | `application/json` (`data` is a JSON object) | same |
| extensions (lowercase alphanumerics, ≤ 20 chars) | e.g. `correlationid`, `causationid`, `actorid`, `actorkind`, `orgid` | `metadata` (closed key set) plus `org_id` | `actor_id`, `actor_kind`, `correlation_id`, `org_id` |

Rules:
- Integration events leave a module as **CloudEvents 1.0 structured JSON** (`application/cloudevents+json`). That way any consumer, including n8n, WAHA hooks or a future broker, reads them without a noc-specific adapter.
- `orgid` travels on every integration event. Tenancy is never inferred.
- Payloads reference people by id; see §5.6 for personal data.

### Contracts: AsyncAPI 3.0 for integration events

- An integration event is a public API. It is declared once in an **AsyncAPI 3.0** document: channel, message, and an operation `send` or `receive`. The document lives beside the producing organ.
- That is the same role OpenAPI plays for our HTTP routes, so the contract-first rule (`noc-contract-first`) applies to events too.
- Internal E1/E2 events need no AsyncAPI document. Their contract is the organ's `event_type` and `schema_version`.

### Delivery: transactional outbox plus idempotent consumer

- **Producer.** The integration event is written to an outbox table **in the same transaction** as the state change and its E1/E2 event. A relay (polling publisher, or log tailing) publishes it after commit. Never dual-write the row and the message (Richardson).
- **Consumer.** At-least-once delivery means duplicates WILL arrive. The consumer records the processed `(subscriber, source, id)` **in the same transaction as its own changes**. A duplicate hits the unique key and is a no-op (Richardson, *Idempotent Consumer*). E2's `es_append` already returns `replayed` for a repeated `event_id`.
- **Ordering.** Ordering is guaranteed per stream or aggregate only. The global feed pages by `(tx_id, global_position)`, so a late-committing transaction is never skipped.

### Versioning

Versioning follows the strategies in Microsoft's Event Sourcing pattern, in this order of preference:
1. **Tolerant reader:** ignore unknown fields and default the missing ones. Use this for additive changes.
2. **Version field:** `schema_version`, or a new `dataschema` URI for a breaking change.
3. **Upcasting on read:** `Upcasters().register(event_type, from_version, fn)`, chained v1→v2→…
4. **In-place rewrite:** the last resort. It breaks immutability and the audit trail, and needs an owner decision.

## 4. When a module is event-SOURCED (E2) and not only logged (E1)

Choose E2 only when **at least one** of these holds:

1. The business needs to know **what was true at a past time T** and that cannot be derived from E1.
   - Example: MRR on a past date — core `/analytics/revenue` rewrote the past from current rows.
2. **Money or legal record**, where corrections must be compensating events, never edits.
   - Examples: ledger, subscription billing, clinical record.
3. **Concurrent writers contend** on one aggregate, and expected-version append is the simplest correct answer.
4. The **intent** of each change matters more than the resulting value.

Stay on E1 when the entity is:
- CRUD reference data, settings, catalogs or lookup tables;
- static data;
- short-lived, or a prototype.

These still log changes (E1) if they carry history. **No events at all** is allowed only for data with no lifecycle and no audit need (pure configuration). If such data later needs an audit trail, it gets E1.

Current E2 picks (owner decisions 2026-11-07):
- core `public.subscriptions`: one stream per subscription, direct cutover, an imported-state event at cutover;
- the finance ledger: stays SQL-summed until a stored projection is MEASURED slow.

## 5. Event rules (every block)

1. **No new hand-written history, movement or `*_eventos` tables.** Use the primitive. Keeper `check_transition_log_hand_written` ratchets the 15-table baseline down; it lands with E1.
2. **Name events by business intent, in the past tense**, e.g. `etapa_alterada`, `opt_out_registrado`, `sessao_realizada`. Never `row_updated`. "Two seats were reserved" beats "seats changed to 42" (Microsoft).
3. **Events are immutable.**
   - A wrong event is corrected by a compensating event.
   - A schema change is handled by a version field plus upcasting on read, never an in-place rewrite.
4. **Legacy rows enter with one `imported_initial_state` event.** History is exact from cutover only, and the docs say so.
5. **Consumers are idempotent** (at-least-once delivery). Projections are rebuildable. A projection that drifts from its events is a bug, which `projection_reconcile` reports.
6. **Personal data (LGPD).**
   - Keep personal data out of event payloads where possible: reference the subject by id.
   - Erasure uses the ONE gated delete-by-subject path (GUC carve-out, owner decision 2026-11-07).
   - Crypto-shredding is not our mechanism. Its legal standing is contested (e.g. treated as insufficient in Germany), and ANPD has not ruled. Anything new here goes to `legal-advisor`.
7. **Events are not async by default.** EOA requires neither a broker nor eventual consistency (Fowler). The default is the same Postgres transaction. Kafka or another stream is never an event store (Dudycz, Microsoft).
8. **Per market, per org.** Events key on canonical roles and slugs (e.g. stage `papel`), never on a market's labels. A role an org's funnel lacks is a declared no-op (`KB § PATTERNS/architect/vertical-seed.md`).

## 6. What this means for each layer

- **Seed:**
  - Every stateful organ ships its E1 log, or E2 stream, as part of the organ: Fake + Real + migration, never "history later".
  - New CRM, ERP and CMS vertical-seed organs are born event-oriented.
  - The seed FUNNEL organ's hand-written `pipeline_movimentos` is the first conversion. It is converted at seed level, never per product.
- **Products:** consume the organ's events. A product-local history table is a fork.
- **Agents (Julia and after):** read state changes as events, never by polling rows. The P5 agents → SW feed is the first integration event.
- **Reviews:**
  - `architect` asks "which block, and why?" for every new table with a status or lifecycle column.
  - `compliance-reviewer` checks §5.

## 7. Enforcement (the build triad)

| Leg | Mechanism | State 2026-11-08 |
|---|---|---|
| Construction | `transition_log_migration`, event store, projections | Queued with the steward; not on `dev` yet |
| Backstop | `check_transition_log_hand_written`; `verify_db_guards` probes | Ships with E1 |
| Telemetry | `noctus.dev.projection_reconcile` | On `dev` (P0) |

Until E1 lands on `dev`, this doc is the declared target and the keeper is not yet blocking. That is stated here so nobody reads the declaration as already enforced.

## 8. Sources (read 2026-11-08)

- Martin Fowler, *What do you mean by "Event-Driven"?* (2017): https://martinfowler.com/articles/201701-event-driven.html
- Microsoft Azure Architecture Center, *Event Sourcing pattern* (updated 2026): https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- Oskar Dudycz, *When not to use Event Sourcing?*: https://event-driven.io/en/when_not_to_use_event_sourcing/ · *Event Streaming is not Event Sourcing*: https://event-driven.io/en/event_streaming_is_not_event_sourcing/
- Greg Young, *A Decade of DDD, CQRS, Event Sourcing* (DDD Europe 2016), reported by InfoQ: https://www.infoq.com/news/2016/04/event-sourcing-anti-pattern
- Arkency, *Event-sourcing whole app — opinions* (Young, Dahan, Pacana): https://blog.arkency.com/event-sourcing-whole-app-opinions/
- Chris Richardson, *Transactional outbox*: https://microservices.io/patterns/data/transactional-outbox
- CNCF, *CloudEvents 1.0 specification*: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
- *AsyncAPI 3.0.0 specification*: https://www.asyncapi.com/docs/reference/specification/v3.0.0
- Chris Richardson, *Idempotent Consumer*: https://microservices.io/patterns/communication-style/idempotent-consumer.html
- RFC 2119 (normative keywords) and RFC 3339 (timestamps)
- Mathias Verraes, *Crypto-Shredding* and *Forgettable Payloads* (2019): https://verraes.net/2019/05/eventsourcing-patterns-throw-away-the-key/ · https://verraes.net/2019/05/eventsourcing-patterns-forgettable-payloads/
