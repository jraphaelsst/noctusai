// SEED-OWNED — thin re-export shim. The real harness-smoke suite (proves
// this product's FE vitest stack actually runs in CI) lives at
// `seed/framework/frontend/src/__harness_smoke__.test.tsx` (absorbed
// 2026-09-20 — was byte-identical across 3 products' local copies, N>=3
// recurrence rule). Mirrors how `vite.config.ts`/`vitest.config.ts` consume
// their seed factories: a thin local file importing the seed implementation.
import "../../../../seed/framework/frontend/src/__harness_smoke__.test";
