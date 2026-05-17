---
slug: whatsapp-intake-monitor
origin:
  - products/youtube-crawler/backend/app/routers/intake_monitor_router.py
  - products/youtube-crawler/backend/tests/routers/test_intake_monitor_router.py
intended_noc_destination: none yet — product-local. The PendingUpload
  state machine this monitor inspects is youtube-crawler-specific
  (real-estate Drive→YouTube upload flow). The conversation-message
  reader it uses (MessageStore over `conversation_messages`) is already
  seed-backed. A generic chatbot-conversation monitor is a future
  seed-lift candidate IF a second chatbot product needs the same
  surface — N=1 today.
layer_rationale: |
  Slice 2 of the WhatsApp-flow management work: a read-only window
  into live WhatsApp conversations (state machine + recent messages)
  plus a stuck-flow cancel. Product-local because the projected state
  (PendingUpload: idle/awaiting_confirmation/awaiting_video_choice/
  processing) is youtube-crawler's intake shape, not a seed concept.
  The durable message history comes from the seed-backed MessageStore,
  so the only product-specific surface is the PendingUpload projection
  + the Redis-key cancel.
seed_first_analysis: |
  Q1 — Cross-product candidate? Partial. A generic "show me my
  chatbot's live conversations + recent messages" monitor would be
  cross-product; the PendingUpload projection is not. Splitting now
  would over-abstract a single consumer.
  Q2 — Variance? High on the state projection (each chatbot product
  has its own state machine); low on the message-history half (already
  seed via MessageStore).
  Q3 — Existing seed coverage? Message store + chat memory are seed.
  No seed conversation-monitor router exists.
  Q4 — Fake+Real? Redis is the IO boundary; the router reads via a
  ``_redis_client`` seam (injectable in tests, mirrors the seed
  Fake/Real factory shape).
  Q5 — Migration cost? Low when a 2nd consumer appears: lift the
  message-history half + a Protocol for the state projection.
  Q6 — Premature-lift risk? Medium-high. Defer until N=2 — recorded
  as accept-with-rationale, not silently skipped.
dependencies_on_other_additions:
  - app/schemas/whatsapp.py Intake* DTOs (left uncommitted — entangled
    with unrelated accumulated VideoCandidateSnapshot work; committed
    by the user)
  - app/main.py router import + registration (same entanglement)
promoted_on: not-applicable (product-local; revisit at N=2)
---

## Why this addition exists

Slice 2 of the WhatsApp-flow management area. After Slice 1
(connection/pairing), this gives operators a read-only monitor of
live inbound conversations: which session is in which intake state,
recent message history, active-upload count, and a one-click cancel
for a stuck flow (clears only the transient Redis pending-state key —
the durable audit log is untouched; the user can re-send immediately).

Endpoints (`/api/whatsapp/intake`): `GET /conversations`,
`GET /conversations/{session_id}`, `POST /conversations/{id}/cancel`.

Verified live end-to-end against the running stack with a real
authenticated test-user JWT (list/detail/cancel/404 + auth gate).
The colocated unit test is correct but the product test harness is
pre-existing-broken outside the uvicorn lifespan (`app.database._db`
is None — the existing `test_dashboard_router.py` fails identically);
that harness gap is flagged separately, not introduced here.

## Caveat (recorded honestly)

Not independently runnable as committed: the `Intake*` DTOs in
`app/schemas/whatsapp.py` and the router import+registration in
`app/main.py` are NOT in this commit — both files carry unrelated
accumulated uncommitted work (the entanglement pattern from Slice 1),
so per the established clean-scope preference they are committed by
the user alongside their accumulated changes.
