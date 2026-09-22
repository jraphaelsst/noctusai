/**
 * useSheetLayout — is the card hub below the `sm` breakpoint (640px)?
 *
 * The LAYOUT itself is CSS (`max-sm:` utilities), so it holds with no JS at
 * all. This hook only surfaces the same decision as `data-layout="sheet" |
 * "dialog"` on the dialog root, so (a) the mobile layout is assertable in
 * jsdom, which evaluates no media queries, and (b) a consumer can branch on it
 * when behaviour — not just styling — differs on a phone.
 *
 * Environments without `matchMedia` (SSR, bare jsdom) report `false`
 * (desktop) — the CSS still switches correctly in a real browser.
 */
import { useEffect, useState } from "react";

export const SHEET_MEDIA_QUERY = "(max-width: 639px)";

function query(): MediaQueryList | null {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  return window.matchMedia(SHEET_MEDIA_QUERY);
}

export function useSheetLayout(): boolean {
  const [isSheet, setIsSheet] = useState<boolean>(() => query()?.matches ?? false);

  useEffect(() => {
    const mql = query();
    if (!mql) return;
    const onChange = (e: MediaQueryListEvent) => setIsSheet(e.matches);
    setIsSheet(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);

  return isSheet;
}
