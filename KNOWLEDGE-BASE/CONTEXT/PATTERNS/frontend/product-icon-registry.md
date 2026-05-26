# Product-icon registry — a product always ships a REAL icon

> **Rule.** A product's `icone` (`core public.products`) MUST render as an actual
> icon — a registered `ProductIcon` name or an emoji — **never the bare TEXT of
> an icon name, never empty.** Render it through the `ProductIcon` component;
> the `ICONS` registry is the single allowlist; the rule is enforced at the
> migration gate, the create-API, and the runtime.

Born 2026-05-25: the Seed (Reference) product was seeded with `icone='Sprout'`,
but `Sprout` was not in the `ProductIcon` `ICONS` map, so the dashboard rendered
the literal word **"Sprout"** instead of an icon. Sibling of
[[product-internal-wiring]] (the data-wiring twin of the same "core admin
surface correct by construction" class).

---

## Why this bites

`ProductIcon` (`products/core/frontend/src/lib/product-icon.tsx`) renders a
product's `icone` field three ways:

| `icone` value | renders as |
|---|---|
| a key in the `ICONS` registry (e.g. `"Building2"`) | the lucide-react **SVG** |
| an emoji / any non-ASCII value (e.g. `"🏠"`) | the value **verbatim** (legacy rows) |
| **anything else** — empty, or an unregistered ASCII name | historically the bare **TEXT** → the bug |

So the moment a product's `icone` is a lucide NAME that nobody added to `ICONS`,
the UI shows the raw string. The same happens for any code that renders
`{product.icone}` inline as text instead of going through the component.

`ICONS` is the **single source of truth** for "renders as a real icon." Adding a
new product icon = import it from lucide-react and add it to `ICONS`.

---

## The four enforcement layers

A half-enforced version (UI only) lets seed migrations slip through, so the rule
is closed at every creation surface.

### 1. Render layer — always via `ProductIcon`, never inline
Every product-icon display goes through `<ProductIcon name={product.icone || 'Box'} color={product.cor} size="sm|md" />`. **Never** render `{product.icone}` as text. Wired across all core surfaces: `Dashboard`, `admin/AdminDashboard`, `admin/AdminProducts` (table + detail), `admin/AdminLogoutBehavior`, `Onboarding`. The component takes a `size` prop (`sm` = h-5, `md` = h-8) so the same component fits cards and dense table rows.

### 2. Runtime safety net — fall back to `Box`, never to text
`ProductIcon` renders a registered name as an SVG, an emoji (non-ASCII) verbatim, and **empty / unregistered ASCII → the `Box` default icon** — a bare lucide name can never reach the screen as text again. This is defence-in-depth; the keeper (layer 4) keeps the data honest so the fallback rarely fires.

### 3. Create-API guard — required + non-empty
`ProductCreate.icone: Field(min_length=1)` (required, non-empty) and `ProductUpdate.icone: Optional[str] = Field(default=None, min_length=1)` (non-empty if supplied) in `products/core/backend/app/schemas/products.py`. A create/patch with an empty or missing icone → **422**. The admin create form (`AdminProducts.EMPTY_PRODUCT_FORM`) defaults `icone: 'Box'`; the scaffolder default is also `"Box"`.

> **Test gotcha.** FastAPI body-validation (422) preempts the auth dependency
> (401/403). Any test that POSTs `/api/products` to assert an auth status MUST
> send a valid `icone`, or it gets 422 instead of the auth code it expects.

### 4. Migration gate (the keeper) — `check_product_icon_registered`
The durable CI/compliance gate (`mcp/noctusai/tools/noctus/dev/compliance.py`, severity `high`, baseline-gated). It **folds the core product-catalog migrations** into the final live catalog and flags any live product whose `icone` is empty or an unregistered ASCII name (emoji allowed).

- **Fold semantics** — INSERT/UPDATE *set*, DELETE *remove*, last-write-wins by (migration number, in-file position). This resolves to the LIVE catalog only, so retired products (`media-scheduling`/`imobi-scheduling`, deleted by `033`) and delete-then-re-add (`seed` → `036` delete, `038` re-add as `Sprout`) validate correctly.
- **Anchor-based parse** (no statement/paren/semicolon parsing — `descricao` text contains both `;` and `()`): `icone` = the quoted token immediately preceding the row's `'http(s)://…'` url_base (only product rows carry a url_base); `slug` = the nearest preceding kebab-case quoted token.
- **Registry source** — parsed from `core/frontend/src/lib/product-icon.tsx` `ICONS`; unreadable registry → the check degrades to `[]` (logged, never crashes).
- Colocated regression test `mcp/noctusai/tests/test_product_icon_registered.py` (`TestCheckProductIconRegistered`); registered in `check_all_products()`.

---

## Checklist — validate a future implementation against this rule

- [ ] New product seeded with a **registered** `icone` (in `ICONS`) or an emoji — never a lucide name you forgot to register. Adding a new lucide name? Import it into `ICONS` **in the same change**.
- [ ] Any UI that shows a product icon renders it via `<ProductIcon>`, not `{product.icone}` text.
- [ ] Create/update payloads send a non-empty `icone` (the form + scaffolder default to `Box`).
- [ ] `noctus.dev.review` / compliance is green — `check_product_icon_registered` returns no new findings.

This is the Stage-4 codification of the rule (memory `feedback_product_icon_must_be_registered` → this doc + `CLAUDE/frontend.md` → the keeper). See `KB § PATTERNS/common/methodology-codification-pipeline.md`.
