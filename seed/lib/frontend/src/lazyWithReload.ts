/**
 * `React.lazy` that survives a deploy happening mid-session.
 *
 * THE FAILURE THIS FIXES
 * ----------------------
 * Vite content-hashes every lazy route chunk (`BaseDeLeads-a1b2c3.js`). A
 * deploy replaces `dist/` with a NEW set of hashed filenames and deletes the
 * old ones. Any browser still holding the PREVIOUS `index.html` — an open tab,
 * a phone that backgrounded the app, anything served from cache — still points
 * at chunk names the server no longer has.
 *
 * The moment the user navigates to a route whose chunk was never loaded into
 * memory, `import()` 404s, `React.lazy` throws, and the ErrorBoundary renders
 * "Algo deu errado".
 *
 * Its signature is confusing enough to send you hunting in the wrong place:
 *
 *   • ONE route breaks, every other route works — because the working ones
 *     were already resolved into memory earlier in that session.
 *   • The SAME page loads fine on another device — which fetched a fresh
 *     `index.html` after the deploy.
 *   • The backend is provably healthy, so the API looks innocent (it is).
 *
 * Reported 2026-08-05: "Base de Leads" failed on mobile while every sibling
 * tab worked and desktop was fine. 23 production deploys landed that day, each
 * re-hashing every chunk.
 *
 * THE RECOVERY
 * ------------
 * Retry the import once (covers a genuinely transient network blip), and if it
 * fails again, force a ONE-TIME hard reload so the browser fetches a current
 * `index.html` and, with it, current chunk names.
 *
 * 🔴 The reload is guarded by a `sessionStorage` flag, and that guard is the
 * load-bearing part. Without it, a chunk that is missing for any OTHER reason
 * (offline, a genuinely broken deploy) reloads → fails → reloads forever. A
 * boot loop is far worse than the error screen it replaces: the user cannot
 * even read the message. One attempt, then let the ErrorBoundary do its job.
 */
import { lazy, type ComponentType } from "react";

const RELOAD_FLAG = "noc:chunk-reload";

/** Vite/webpack phrase these differently across browsers; match the union
 *  rather than one engine's wording. Anything unrecognised is re-thrown
 *  untouched — a real component bug must never be mistaken for a stale
 *  chunk and papered over with a reload. */
function isStaleChunkError(error: unknown): boolean {
  const message = String((error as Error)?.message ?? error ?? "");
  return (
    /Failed to fetch dynamically imported module/i.test(message) ||
    /error loading dynamically imported module/i.test(message) ||
    /Importing a module script failed/i.test(message) ||   // Safari
    /ChunkLoadError/i.test(message) ||
    /Loading chunk .* failed/i.test(message)
  );
}

export function lazyWithReload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      const mod = await factory();
      // A successful load means whatever chunk set we are on is coherent —
      // clear the guard so a LATER deploy can recover the same way.
      try {
        sessionStorage.removeItem(RELOAD_FLAG);
      } catch {
        // Private-mode Safari throws on sessionStorage. Not being able to
        // clear the flag costs one future recovery, never correctness.
      }
      return mod;
    } catch (error) {
      if (!isStaleChunkError(error)) throw error;

      // One retry: distinguishes a dropped request from a genuinely absent
      // file, and costs one round trip.
      try {
        return await factory();
      } catch {
        /* fall through to reload */
      }

      let alreadyReloaded = false;
      try {
        alreadyReloaded = sessionStorage.getItem(RELOAD_FLAG) === "1";
        if (!alreadyReloaded) sessionStorage.setItem(RELOAD_FLAG, "1");
      } catch {
        // Storage unavailable ⇒ we cannot prove this is the first attempt.
        // Treat it as "already reloaded" and surface the error instead of
        // risking an unbreakable reload loop.
        alreadyReloaded = true;
      }

      if (!alreadyReloaded) {
        window.location.reload();
        // Never resolves — the reload tears the page down. Returning a
        // pending promise stops React rendering an error frame first.
        return new Promise<{ default: T }>(() => {});
      }
      throw error;
    }
  });
}
