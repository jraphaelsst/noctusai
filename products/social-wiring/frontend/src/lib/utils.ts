/**
 * Shared utility functions for Social Wiring frontend.
 *
 * Re-exports the canonical helpers from `@noctusai/lib/utils` so product
 * code imports `cn`, `formatCurrency`, `formatDate`, `getTodayAtMidnight`,
 * `stripTime` from `@/lib/utils` (one local import) instead of crossing
 * the seed boundary in every component. Mirrors the 5-product convention
 * (core, dev-team, ERP, PF, therapy) and the live-validated CMS source.
 *
 * Add product-specific helpers below the re-export (e.g., a `slugify`
 * for the video URL scheme). Don't redefine helpers that already live
 * in the lib — if you find yourself copying one, lift it to
 * `@noctusai/lib/utils` instead (recurrence rule).
 */
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from "@noctusai/lib/utils";
