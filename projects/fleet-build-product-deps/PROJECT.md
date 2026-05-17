# fleet-build-product-deps — Project Document

> Living stub. Filed 2026-05-16 as the named destination for a **pre-existing** per-product Docker-build dependency defect surfaced (NOT caused) by the social-wiring-absorption Wave-6 cold full-fleet build. Self-contained — references code paths + dated facts only.

- **Created:** 2026-05-16
- **Status:** Filed / not started
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `fleet-build-product-deps` (cross-product / infra → `projects/fleet-build-product-deps/`)

## 1. Context & Purpose

The social-wiring-absorption Wave-6 resumed the whole-fleet `./start.sh full` build for the consolidated 9-product topology. `social-wiring` itself builds cleanly (the absorption deliverable — verified `ghcr.io/jraphaelsst/noctus-social-wiring:dev`, 2026-05-16). The fleet build, however, fails on **`erp-imobiliario`** at `pip install -r requirements.txt`: `pycairo>=1.20.0` (chain `xhtml2pdf>=0.2.0 → svglib → rlpycairo → pycairo`) `metadata-generation-failed` — `pycairo` is a C-extension that needs system `libcairo2-dev` + `pkg-config` present at build time, which the slim runtime image stage lacks. **Pre-existing** (this branch never modified `products/erp-imobiliario/backend/requirements.txt`); out of absorption scope; surfaced by the cold build (the "image build is the real oracle" lesson). A 2nd-attempt unrelated env failure (Docker-VM disk-full) was already remediated separately.

## 2. Scope

- Fix `erp-imobiliario`'s Docker build: either add the `libcairo2-dev`/`pkg-config` apt deps to its Dockerfile build stage (or the shared seed base if N≥2 products need cairo — recurrence check), OR pin/replace the `xhtml2pdf`/`svglib` chain to a wheel-shipping version that doesn't compile `pycairo`.
- Re-run `./start.sh full` for the full 9-product fleet; confirm every product (incl. erp-imobiliario) builds + the house single-container model comes up green (no `noctus-seed` collision — already fixed in W6.0).
- Sweep the other surviving products for the same cold-build-only C-extension class while at it (N-recurrence: if ≥2 need cairo/build-deps → seed base image, per "no quick fixes / fix at root").

## 3. Prerequisites / gate

None — independently actionable. Does NOT gate the social-wiring-absorption project (that delivered the absorbed product + the correct consolidated containerization refactor; social-wiring builds). This is the residual "whole-fleet-green" item, separated by scope discipline.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the named destination for the pre-existing erp-imobiliario pycairo/xhtml2pdf Docker-build-dep defect surfaced by social-wiring-absorption Wave-6. | Claude Opus 4.7 |
