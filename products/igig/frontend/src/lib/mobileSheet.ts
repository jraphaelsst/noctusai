/**
 * Roadmap R0 (mobile-first): below the `sm` breakpoint (640px) a modal is a
 * full-screen sheet. Passed as `className` to the seed inline `Dialog` panel
 * (directly, or through `EntityDetailDialog`), whose backdrop keeps a `p-4`
 * gutter and a centered `max-w-md` card — fine on desktop, cramped on a phone.
 * `max-sm:` utilities only, so ≥640px renders exactly as the seed designed it.
 *
 * NOC-REMEDIATE[seed-dialog-mobile-sheet]: the seed `Dialog` should be a sheet
 * <640px by construction (MotivoMoveDialog + CardHubDialog already carry their
 * own copy of this class list on the Radix dialog) — lift it there. — 2026-09-23
 */
export const SHEET_MOBILE =
  "max-sm:fixed max-sm:inset-0 max-sm:h-[100dvh] max-sm:max-w-none " +
  "max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0";
