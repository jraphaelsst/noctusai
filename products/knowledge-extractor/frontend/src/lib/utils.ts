/**
 * Shared utility functions for Knowledge Extractor frontend.
 *
 * Re-exports the canonical helpers from `@noctusai/lib/utils` so product
 * code imports `cn`, `formatDate`, `getTodayAtMidnight`, `stripTime`
 * from `@/lib/utils` (one local import) instead of crossing the seed
 * boundary in every component. Mirrors the multi-product convention
 * (core, social-wiring, ERP, PF, therapy).
 */
export { cn, formatDate, getTodayAtMidnight, stripTime } from "@noctusai/lib/utils";
