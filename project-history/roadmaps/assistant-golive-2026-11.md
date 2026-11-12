# Assistant: go-live roadmap (2026-11)

> Milestone bullets get ✅ only when genuinely reached. `M4` is the prod-promotion milestone referenced by
> `deploy/consent/assistant.prod.yml` (`KB § PATTERNS/devops/prod-exposure-consent.md`).
> Plan of record: `project-history/assistant-chatbot/phase0-d46-shadow-line.md` (D46 shadow line, D48 no reply/send).

## Milestones

- **M1: product + read-only shadow line**: seed scaffold, WhatsApp connections + webhook mount (HMAC required), intake rows with HMAC'd `chat_ref`, no send path (D48). ✅ reached 2026-11-10 (`dbc49fa1b`, `1a8afcc4d`).
- **M2: classifier, labelling, Google connect**: Haiku scheduling classifier (S3), blind labelling page (S4), in-app Google Calendar/Drive connection (S7), owner-hand pairing gate. ✅ reached 2026-11-11 (`d8cefe3e6`, `fab1de373`, `c16c9cd2e`).
- **M3: dev validation**: deploy wiring (S6A) and the no-leak HTTP error bodies landed through the merge queue with the merged tree CI-green; migrations 001–019 on dev; pre-live security + AI-path audit with no P0/P1 (D51 accepts password-only admin sign-in for now). ✅ reached 2026-11-12 (`264f31b67`, `5e30f5298`).
- **M4: prod promote**: ✅ authorized 2026-11-11 by the owner in-session ("i allow all migrations to be applied, also all to go to prod and deploy live."; owner-ask tier; consent record `deploy/consent/assistant.prod.yml`). The ✅ marks the authorization; the cutover items below stay open until reached.
  - ✅ Dev validation (M3) complete.
  - ⬜ Prod registration (compose service, tunnel ingress, config template).
  - ⬜ `predeploy_check assistant` ready on the integrated tip; core 119 + assistant 001–019 applied; secrets set; image deployed; DNS.
  - ⬜ Live probe (curl expected codes + browser), per `feedback_security_as_build_pattern`.
- **M5: owner pairs the personal line**: owner-hand apply in Terminal.app, QR scan on Conexão, Google redirect URI + scopes in Cloud Console. ⬜ Owner's hand only.
