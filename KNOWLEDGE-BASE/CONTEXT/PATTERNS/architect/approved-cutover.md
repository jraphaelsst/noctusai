# Approved cutover — ship the next version early, switch only on the owner's approval, retire the old one after a validation window

> **Rule.** When an external change is coming on a known date or signal (a new tax system, a provider API version, a regulation), build **both** variants behind one Protocol now. At the trigger, the system raises a **danger alert with an Approve button** — it never switches by itself. After approval, the old variant stays installed for a **validation window** so it can be switched back; only after the window closes clean is the old code deleted.

Born 2026-10-12 (commerce seed, decision D19): Simples Nacional businesses must issue service invoices through the national NFS-e system from 1 Nov 2026. Owner: *"build the current for validation, but also build the new one; when the change comes I get a warning with an approval button and a danger sign … after we change, keep the old code for a while so we validate the operation with the new code before discarding the old code."*

---

## 1 · Shape

| Piece | What it is |
|---|---|
| **Two adapters, one Protocol** | `current` + `next`, both Real, both with the shared Fake for tests (`../backend/seed-fake-real-adapter.md`). The factory picks the variant from an org setting `<capability>_variant`. |
| **Cutover record** | one row per capability: `capability`, `current`, `next`, `trigger` (date and/or signal), `status` (`scheduled → alerting → approved → validating → retired` or `postponed` / `rolled_back`), `approved_by`, `approved_at`, `validation_until`, `retire_after`. |
| **Trigger watcher** | a scheduled check: when the trigger is reached (or `lead_days` before it), status → `alerting` and a danger alert goes to the product admin + the platform owner (seed in-app notifications; WhatsApp/email optional). |
| **Danger alert** | names what is changing, the legal/provider reason, the date, what happens if nobody acts, and offers **Approve switch** / **Postpone** (with reason). Never auto-approves. |
| **Validation window** | after approval, `next` is live and `current` stays registered; the admin can roll back with one action (audited). Health metrics per variant (success rate, error count, provider rejects) shown side by side. |
| **Retirement gate** | when `validation_until` passes with metrics clean, status → ready-to-retire; the old adapter carries a `NOC-REMEDIATE[cutover-retire]` marker with the date, so the deletion lands in a normal reviewed commit. |

## 2 · Rules

- **The switch is the owner's decision**, recorded with who/when (same principle as `../devops/prod-exposure-consent.md`: an agent may record a decision, never invent one).
- **Per org.** Clients can be on different variants during the window (one client approves earlier, another later); the platform owner sees all.
- **Both variants tested continuously** until retirement — the `next` adapter is exercised against its sandbox before the trigger, not first on the day.
- **No silent fallback.** If `next` fails after approval, it fails loudly (alert + error to the operator); falling back to `current` is a deliberate rollback action, never automatic.
- **Retire for real.** Leaving the old variant forever is a half-migration; the remediation marker makes the leftover visible to `noctus.dev.scan_remediation_markers`.

## 3 · Commerce instance (D19)

`invoice_variant`: `current` = issuance through the provider/municipal flow used today; `next` = NFS-e Nacional (national emitter API). Trigger: 2026-11-01 for orgs whose tax regime is Simples Nacional (regime is a store-profile field). NF-e for goods is unaffected. Built in roadmap phase P4.

## Composes with

`vertical-seed.md` · `../backend/seed-fake-real-adapter.md` · `../common/remediation-markers.md` · `../devops/prod-exposure-consent.md`.
