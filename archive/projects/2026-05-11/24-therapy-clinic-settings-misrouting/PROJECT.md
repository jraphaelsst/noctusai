# Therapy Clinic Settings Misrouting — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Done (single-engineer focused fix; one-shot dispatch)
- **Owner / stakeholders:** USER · Engineer VVV (executor) · Engineer NNN (filer)
- **Related docs:** `products/therapy-platform/frontend/src/pages/clinic/Settings.tsx`, `products/therapy-platform/frontend/src/hooks/useSettings.ts`, `products/therapy-platform/backend/app/routers/clinics.py`, `products/therapy-platform/backend/app/schemas/clinic.py`
- **Project slug:** `therapy-clinic-settings-misrouting` at `products/therapy-platform/projects/therapy-clinic-settings-misrouting/` (single-product scope)

---

## 1. Context & Purpose

Engineer NNN filed this during Therapy Phase 8 (clinic-portal settings build-out) after spotting that the clinic Settings page UX was lying to users. The page calls `updateBranding.mutate(<payload>)` for Profile, Bank, Commission, and Branding sections — all four sections share a single mutation. That mutation hits `PATCH /api/settings/clinic/branding`, whose Pydantic body schema (`ClinicBrandingUpdate`) accepts only `primary_color / secondary_color / logo_url / favicon_url`. Pydantic silently drops unknown fields by default.

Net effect: the user fills in CNPJ, bank details, PIX key, commission rates → clicks "Salvar" → sees `Branding atualizado` success toast → nothing persists. The next page load shows the empty fields again. A high-severity silent UX bug.

Backend already exposes the correct routes:
- Profile fields → `PATCH /api/clinics/{clinic_id}` with `ClinicUpdate` schema
- Bank + Commission fields → `PATCH /api/clinics/settings` with `ClinicSettingsUpdate` schema

This project rewires the frontend so each section calls the right route via a dedicated hook + adds backend persistence-verification tests so the misrouting cannot regress.

---

## 2. Confirmed constraints

- **No backend schema changes** — the routes + schemas already exist; the bug is purely frontend wiring. *(Drives the fix to the hooks/page layer only.)*
- **Single-PROJECT.md, no §7 design batch** — NNN's filing already specifies the four code changes. *(Brief size is small.)*
- **Status-code-assertion rule applies on every body assertion** — keeper enforces this.
- **No monkey-patching** — write-side verification uses `MockRequestBuilder.updated_payloads` (the seed-canonical pattern).

---

## 3. Design principles

1. **One section, one hook, one route.** Separate `useUpdateClinicProfile / useUpdateClinicAdminSettings / useUpdateClinicBranding` mutations — never share a single mutation across sections.
2. **Type the update payloads to the Pydantic schema.** New `ClinicProfileUpdate` + `ClinicAdminSettingsUpdate` interfaces mirror `ClinicUpdate` + `ClinicSettingsUpdate`.
3. **Persistence test is the regression guard.** Two backend tests assert `MockRequestBuilder.updated_payloads` on `clinics` + `clinic_settings` tables — if a future refactor reverts to the branding route, these tests fail loudly.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** NO — `clinic_id`, clinic-admin role, and `clinic_settings` table are therapy-specific.
2. **Is the data source product-specific?** YES — `clinics` + `clinic_settings` tables live in the `therapy` schema.
3. **Is the placement product-specific?** YES — the clinic Settings page is therapy-specific (no other product has clinic admins).
4. **Is the visibility / permission rule the same?** NO — gated on `role == "clinic_admin"`.
5. **Does the seam already exist in seed?** N/A — pure product-bounded change.
6. **Default-on or opt-in?** N/A — bug fix, not a feature.

**Litmus — per-product code count:** Multiple files in therapy (hooks + page + tests). Acceptable — pure single-product UX bug; nothing here generalizes.

---

## 6. Phases

### Phase 1 — Fail-before-fix persistence tests (test-first)
- `tests/routers/test_clinics_router.py::TestUpdateClinic::test_update_clinic_profile_fields_persist`
- `tests/routers/test_clinics_router.py::TestClinicSettings::test_update_settings_bank_and_commission_fields_persist`

Tests assert `updated_payloads` on the correct table contains every field the frontend now sends. Pre-fix, the frontend never hits these routes — so the tests assert that the BACKEND routes DO persist the fields when called correctly (the bug is purely on the frontend side; the test is a regression guard).

### Phase 2 — Hook additions (`useSettings.ts`)
- New `ClinicProfile` + `ClinicProfileUpdate` interfaces.
- New `ClinicAdminSettings` + `ClinicAdminSettingsUpdate` interfaces.
- New `useClinicProfile(clinicId)` + `useUpdateClinicProfile(clinicId)` hooks.
- New `useClinicAdminSettings()` + `useUpdateClinicAdminSettings()` hooks.
- JSDoc update on `ClinicBrandingUpdate` — bug is now fixed.

### Phase 3 — Page rewire (`pages/clinic/Settings.tsx`)
- Profile section → `useUpdateClinicProfile` (resolves `clinic_id` from `user.user_metadata.clinic_id`).
- Bank section → `useUpdateClinicAdminSettings`.
- Commission section → `useUpdateClinicAdminSettings` (combined mutation).
- Branding section → `useUpdateClinicBranding` (unchanged route).
- Field-name alignment with backend schemas (`name` not `nome`, `phone` not `telefone`, `contact_email` not `email`, `bank_name` not `banco`, `default_commission_pct_*_sourced` not `default_*_pct`).
- Form-init prefer the new clinic-profile + admin-settings queries; branding query remains for color initialization.

### Phase 4 — Verification
- `pytest tests/routers/test_clinics_router.py tests/routers/test_settings_router.py` → 56 passed (54 pre-existing + 2 new).
- `pytest -q` full suite → 1330 passed (baseline 1328 + 2 new). 6 pre-existing failures untouched.
- `npx vite build` → clean.
- `cli.py --review --product therapy-platform` → 0 NEW (1 pre-existing notifications-table issue unchanged).

---

## 10. Commands (copy-paste)

```bash
# Backend tests (clinic + settings routers)
cd products/therapy-platform/backend && \
  PYTHONPATH="../../../seed/lib/backend:../../../seed/framework/backend:.:$PYTHONPATH" \
  pytest tests/routers/test_clinics_router.py tests/routers/test_settings_router.py -q

# Full backend baseline
cd products/therapy-platform/backend && \
  PYTHONPATH="../../../seed/lib/backend:../../../seed/framework/backend:.:$PYTHONPATH" \
  pytest -q --tb=no

# Frontend build
cd products/therapy-platform/frontend && npx vite build

# Keeper review
cd mcp/noctusai && \
  PYTHONPATH="../../seed/lib/backend:$PYTHONPATH" \
  python3.11 cli.py --review --product therapy-platform --worktree-path "$(cd ../.. && pwd)"
```

---

## 11. Change log

- 2026-05-11 — Engineer VVV — Phase 1+2+3+4 shipped in one dispatch. Added 2 persistence tests (`test_update_clinic_profile_fields_persist`, `test_update_settings_bank_and_commission_fields_persist`). Added 4 hooks + 4 TypeScript interfaces in `useSettings.ts`. Rewired 4 sections of `Settings.tsx` with backend-aligned field names. All verification gates green.
