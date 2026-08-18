# ImovelWeb portal leads — handoff

> **Everything buildable without credentials is built.** Seed package, MCP
> connector, product slice and frontend are all on
> `feat/imovelweb-portal-leads`, rebased onto `origin/dev` (the OLX branch had
> already merged, so this IS the merged tip). The one remaining input is
> **sandbox credentials**, and that is a request to the vendor, not a task.
>
> **Nothing is live.** The receiver 401s every delivery until a secret is
> configured (`bypass_when_unset=False`), the migration is a file that has not
> been applied to any database, and the connector is not registered in
> `.mcp.json`. Merging this is safe; *calling* the integration is what needs
> Gate 2.

**Date:** 2026-08-18 · **Branch:** `feat/imovelweb-portal-leads` (local, unpushed)

---

## 1 · The one thing that is blocked

**Send the credential request.** The email is drafted and ready at
`gate-1-credential-request.md`, addressed to `integracao@imovelweb.com.br`.
It carries **one open decision** that is the user's, not an engineer's:

| | ReadOnly *(drafted)* | Read-and-Write |
|---|---|---|
| The two lead events | ✅ | ✅ |
| `AVISO_*` listing events | ❌ | ✅ |
| Also grants | nothing | publish / unpublish / delete clients' listings |
| API surface it opens | the ~15 endpoints we use | **~55** — 40 more, almost all listing publication |

Read-and-Write is not "the same integration plus four event types": it opens
the publication API, which is the territory `products/erp-imobiliario`
already reaches by XML feed. A second writer to the same listings is an ERP
design decision. **Recommendation: ReadOnly**, and request write separately
later if a feature ever needs it — nothing here would be rebuilt.

The vendor issues credentials twice: once for sandbox, again for production
after testing. Both are separate emails.

---

## 2 · What the credentials unlock, in order

Gate 1 is scripted end-to-end and needs no new code. Run it through the
connector (`python mcp/imovelweb/server.py`, or drive the tools directly):

1. `imovelweb.diagnostics.connection_status` — answers from a live session.
2. `imovelweb.diagnostics.probe` — correct `IMOVELWEB_ENDPOINT_BASELINE` from
   what was **observed**, never guessed.
3. `imovelweb.agencies.list` — ≥1 authorized agency; confirms **we** choose
   `CODIGOIMOBILIARIA`, which is what makes tenant resolution a pure lookup.
4. `imovelweb.callbacks.put_config confirm=true` then `.get_config` — the
   registration reads back identically.
5. `imovelweb.sandbox.emit_event` — **the instrument this whole project is
   sequenced around.** It asks the vendor to push a real `CONTACTO_MENSAJE`
   at our receiver, so the contract is provable before a single real lead
   exists. Grupo OLX had no equivalent; that is why its Gate 1 needed
   production traffic and this one does not.
6. `imovelweb.webhook.record_delivery` then `imovelweb.contract.diff_observed`
   — the doc-vs-reality loop. Fix `contract.py` FIRST, then date the
   observation in `KB § INTEGRATIONS/imovelweb.md § 8`, then flip `verified`.
7. **Measure pre-response latency.** If p99 > 1.5 s the handler shape needs
   revisiting before Phase C is trusted — see §4 below.
8. `GET /v1/contatos/acoes` replaces the transcribed `IMOVELWEB_CONTACT_TYPES`.
9. Reconcile a lead end to end: emit, blackhole the callback, run reconcile,
   prove it lands **exactly once**.

---

## 3 · The questions only live traffic can answer

These are recorded as UNVERIFIED in the code, not guessed around:

- **Which language variant to register.** No variant carries both the agency
  code and `leadOrigin`: EN2 has the portal name and no agency code; PT/ES/EN
  have the agency code and no portal name. The parser auto-detects and the
  contract is language-parameterized, so this is a *default*, not an
  assumption — but the choice decides whether org-resolution rung 1 exists.
- **`phone` vs `phoneNumber`.** The vendor documents `phone` as
  international-with-`+` AND `phoneNumber` as "ddd + phone". Both cannot hold.
  `full_phone` is defensive; one delivery settles it.
- **`Mensaje.idMensaje` vs the callback's `messageId`.** Same id space or
  not (Gate 0.6). The `messageId` twin guard means reconciliation is already
  safe either way, but the answer belongs in the KB.
- **Rate limits.** Undocumented anywhere. Record the 429s, or record that
  none appeared over N calls.

---

## 4 · Two things deliberately left as they are

**`record_event` is a SELECT + INSERT, not an upsert.** Two round-trips
inside a 1.5-second budget. The single-write fix is real, and it is blocked
on `MockRequestBuilder.upsert()` still being a no-op — an upsert path would
test green and duplicate in production. Teaching the mock conflict-target
propagation changes test behaviour at ~70 call sites across the fleet, so it
is its own work. Marked in-code as `NOC-REMEDIATE[perf-single-write]`, and
Gate 1.7 measures whether it actually matters before anyone schedules it.

**No retention job yet.** `imovelweb_lead_events.payload` and
`imovelweb_leads.raw` can hold a CPF and are never cleared. The design is
written down (NULL the payload on processed rows past the horizon, KEEP the
row — the id is the dedup key, and deleting it lets a late redelivery
re-ingest the lead) and flagged in `LGPD-WARNINGS.md`. It is blocked on the
user choosing N.

---

## 5 · Findings handed to other owners

- **Migration 051's service-role policies are invisible to the keeper.** It
  named them `olx_lead_events_service_role` / `olx_leads_service_role`;
  `check_admin_endpoint_service_role_bypass` matches the **literal** name
  `service_role_bypass`. 052 uses the literal name. 051 has merged, so fixing
  it is now an ordinary follow-up rather than a cross-branch edit.
- **`routers/olx_webhook.py` returns full lead PII.** `GET /events` does
  `.select("*")`, which includes `payload` — the whole vendor body — to any
  authenticated org member. The ImovelWeb route selects an explicit column
  list instead. Worth fixing on the OLX side.
- **Cross-pipe duplicates are now possible in production.** An advertiser
  live on both Grupo OLX's ImovelWeb bridge and our direct integration
  receives each enquiry twice, under two vendor ids, and
  `uq_sw_leads_org_external_lead` will not catch it because
  `external_source` differs. Gate 2.6 asks the question per advertiser.
  Deliberately not solved with a fuzzy key: surfacing a duplicate-SUSPECT
  count is advisory, and merging is a human decision.

---

## 6 · Verification (all by exit code, never a piped `tail`)

```bash
cd seed/lib/backend        && python -m pytest -q                    # 3188 passed, 1 skipped
cd mcp                     && python -m pytest imovelweb/tests _kit/tests -q  # 113 passed
cd products/social-wiring/backend  && python -m pytest -q            # 2092 passed, 3 skipped
cd products/social-wiring/frontend && npx vitest run && npm run build && npx tsc --noEmit
python mcp/noctusai/cli.py --verify-kb-sync
python mcp/noctusai/cli.py --scan-wiring social-wiring
```

Worktree note: `node_modules` must be symlinked from the primary checkout for
`products/social-wiring/frontend`, `seed/lib/frontend` and
`seed/framework/frontend`, or vitest cannot load its config.

---

## 7 · Registering the MCP connector

`.mcp.json` is gitignored, so the row is applied by hand — and **only after
this branch merges into `dev`**. The `cwd` points at the primary checkout,
whose editable `noctusai_lib` has no `integrations.imovelweb` until then; the
server would `ImportError` at every session start. Until the merge, drive it
over stdio from the worktree. Keep-list membership is the user's call.

```json
"imovelweb": {
  "command": "<repo>/venv/bin/python",
  "args": ["<repo>/mcp/imovelweb/server.py"],
  "cwd": "<repo>"
}
```
