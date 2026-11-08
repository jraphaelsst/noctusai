# Marketing organs and Motion — animation enters the fleet through ONE subpath

> **Rule.** Motion (npm `motion`, formerly `framer-motion`) is imported **only** through `@noctusai/lib/marketing`. No product, no template file and no other seed-lib module imports `motion`, `motion/react`, `motion/react-*`, `motion/*` or `framer-motion`.
>
> **Why.** The seam's `MotionProvider` hard-codes `MotionConfig reducedMotion="user"` + `LazyMotion strict`. A product that never touches motion directly cannot forget reduced-motion and cannot pull motion into an authenticated app chunk. Both failures are invisible in review and in unit tests; only the import boundary prevents them.
>
> **Mechanism.** Construction: the `marketing/` directory of the seed lib frontend (the `@noctusai/lib/marketing` subpath, shipped by the sibling slice) and its organs. Backstop: keeper `check_motion_import_boundary` (`--check-motion-import-boundary`, high, pre-commit warn-first shadow, ts-morph AST scan `mcp/noctusai/node/motion_import_scan.mjs`, no baseline). Telemetry: the cli exit wrapper logs every run; walls rank in `--gate-alignment walls`.

## Shape

- **Peer dependency.** `motion` is a peer dependency of `@noctusai/lib`, reachable only via the subpath `@noctusai/lib/marketing`. The main barrel never re-exports it.
- **Landing chunks only.** Marketing organs load in landing routes. Authenticated app chunks must not import them, so motion stays out of the app bundle.
- **Reduced-motion is built in.** It lives in the provider (`reducedMotion="user"`), not in each organ and not in each product.
- **SSR is never prerendered hidden.** Server-rendered content is never emitted at `opacity: 0` or any hidden initial state; animation enhances visible content (initial state = final state until hydrated). Crawlers, no-JS visitors and LCP all see the content.
- **LazyMotion strict.** Organs use the `m` components with feature bundles loaded lazily; a stray full `motion.*` component throws in dev.

## The planned organ set

LandingNav · Hero (with a media slot) · FeatureGrid · Steps · CtaBand · LandingFooter. Piloted on `core`, `social-wiring` and `agents` before fan-out (pilot-products-first); products consume the organs and compose copy and media through slots, never fork them (`KB § PATTERNS/architect/products-consume-canonical-organs.md`).

## Landing organs v2: opt-in props, product brand, cross-product URLs

Product landings match their approved mockup through **opt-in props on the same organs** (a default render is unchanged, so core is untouched): Hero `variant="inverse"` / `bareMedia` / `accentEmphasis` / `stats` / `entrance="staggered"`; FeatureGrid `columns={2}` / `cardVariant="large"` / `accent` / `revealItems` and per-item `tag` / `bullets` / `link`; LandingNav omits the Produtos disclosure unless `products` is passed (`loginAlwaysVisible`, `primaryActionDesktopOnly`); LeadCaptureForm `variant="product"` + `productInterest` + copy overrides; CtaBand `variant="inverse"`; LandingFooter `tagline` as a node. The 3-state theme (`LandingThemeProvider`, `ThemeSwitch`) and the non-core lead wire (`createCoreLeadSubmit`, to `env.CORE_API_URL`) live in the seed, not in products.

**Product brand precedence** (highest first): element override (`link.brand`) > `<ProductBrandScope brand>` (static per-product accent, CSS variables on a scoped `display: contents` element, never `:root`) > org `BrandProvider` (runtime `/api/brand/current`) > NOC tokens. The accent text uses `primary` on light and `primary-light` on dark; a declared accent must reach AA for white-on-primary, accent text on the light/dark/inverse surfaces and the dark focus ring. Landings use the system font (no heading font in the contract).

**Another product's public URL** in the FE is `productUrl(slug, path?)` from `@noctusai/lib`, the mirror of the backend `resolve_product_url`: `VITE_PRODUCT_URL_<SLUG>` > `VITE_PRODUCT_URL_PATTERN` > `https://<slug>.noctusai.com`. Short-host products (erp, social, core) pin it with the per-product variable; do not read `VITE_<PRODUCT>_URL` ad hoc.

## What the keeper checks

- **Fails** on any import, `export … from`, dynamic `import()` or `require()` of `motion`, `motion/*`, `framer-motion` or `framer-motion/*` in `products/*/frontend/src/**` (active products only, `deploy/fleet/active-scope.txt`), `templates/product-seed/frontend/src/**`, and `seed/lib/frontend/src/**` outside `marketing/`.
- **Allows** imports from `@noctusai/lib/marketing`, look-alike packages (`react-motion`, `motion-canvas`), and the `marketing/` directory itself. It does not require that directory to exist.
- **Escape.** `// noc-allow: motion-import — <why>` on the import line or up to 3 lines above; a bare marker without a reason does not count.
- **A scan that cannot run** (no node, ts-morph missing) is one explicit finding, never a silent pass.

## Revisit triggers

Reopen this decision when any of these holds:

1. The Motion licence changes.
2. Landing LCP regresses by more than 200 ms after adopting the organs.
3. A product needs layout animation (`domMax`, about 38 KB) — decide a second, explicit subpath instead of a direct import.

## Related

`KB § PATTERNS/design/design-craft-canon.md` §5.6 (motion craft) · `KB § PATTERNS/common/gate-methodology-sync.md` (build triad) · `KB § PATTERNS/architect/products-consume-canonical-organs.md`.
