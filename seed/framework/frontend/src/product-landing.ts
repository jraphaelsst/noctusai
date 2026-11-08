import { writeEntryMarker } from "@noctusai/lib";

/**
 * Where a sign-out lands: THIS product's own public landing (owner decision
 * 2026-11-08; before that, SSO products sent the user to core's landing).
 *
 * "/" on the product's own origin is the one universal answer, because
 * `createProductApp` already serves it to a signed-out visitor: the product's
 * `Landing` when it has one, otherwise a redirect to its `unauthRedirect`
 * (e.g. core: Landing at "/", `unauthRedirect: '/login'`). It is a PUBLIC route
 * and nothing there auto-launches SSO, so a global sign-out is not bounced back
 * in. A relative path keeps the user on the product's origin (agents.* stays
 * on agents.*) with no per-product configuration.
 */
export const PRODUCT_LANDING_PATH = "/";

/**
 * Hard-navigate to the product landing (full reload drops in-memory state).
 *
 * Reached after Sair, so it also stamps the entry marker `signed-out`: the next visit to "/" shows
 * the Landing (no silent re-entry through core), and sibling tabs that lose the session land on "/".
 */
export function goToProductLanding(
  navigate: (url: string) => void = (url) => {
    window.location.href = url;
  },
): void {
  writeEntryMarker("signed-out");
  navigate(PRODUCT_LANDING_PATH);
}
