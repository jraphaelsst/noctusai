/**
 * useActiveAccount — lightweight Zustand store holding the active account/client
 * selection for the product's data views (YouTube, Meta, n8n, WhatsApp).
 *
 * Persisted to localStorage so the selection survives navigation between pages
 * within the same session.
 *
 * ─── Why the selection is keyed BY PROVIDER ──────────────────────────────
 *
 * It used to be a single `activeAccountId` shared by every page. An
 * `integration_accounts.id` is only meaningful to the provider that owns it,
 * and every provider-scoped hook sent this one id to its own provider's
 * endpoint — so navigating Meta → n8n put the Meta account id on
 * `GET /api/n8n/workflows?account_id=…`, which the backend correctly
 * rejected. That was the live 404 on 2026-07-31: the id in the request
 * belonged to `provider='meta'`, and the org's only n8n account was a
 * different row entirely.
 *
 * `ConnectedAccountSwitcher` did carry a reconcile effect for exactly this,
 * but it can only run AFTER `/api/integrations/accounts?provider=…`
 * resolves, and the data queries fire on the same render — so the bad
 * request is already in flight by the time the selection is repaired. A
 * post-hoc repair cannot fix a race; keying the state correctly can.
 *
 * With the selection keyed by provider, a page can only read the id chosen
 * FOR it: the cross-provider leak is unrepresentable rather than merely
 * reconciled. Removing the old flat field is deliberate — it turns every
 * unmigrated read into a compile error instead of a silent wrong-id request.
 *
 * Usage:
 *   const accountId = useActiveAccountId("youtube");   // read (provider-scoped)
 *   const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);
 *   setActiveAccount("youtube", id);                   // write
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ActiveAccountState {
  /**
   * Per-provider account selection, keyed by provider slug ("youtube",
   * "meta", "n8n", "whatsapp", …). A missing key — or an explicit null —
   * means "org default" for that provider. Prefer `useActiveAccountId(
   * provider)` over reading this map in a component.
   */
  activeAccountIdByProvider: Record<string, string | null>;
  /** The currently selected client UUID; null = all clients / unfiltered. */
  activeMarcaId: string | null;
  setActiveAccount: (provider: string, accountId: string | null) => void;
  setActiveMarca: (marcaId: string | null) => void;
  /** Convenience: clear the client and every provider's account selection. */
  clearSelection: () => void;
}

export const useActiveAccountStore = create<ActiveAccountState>()(
  persist(
    (set) => ({
      activeAccountIdByProvider: {},
      activeMarcaId: null,
      setActiveAccount: (provider, accountId) =>
        set((state) => ({
          activeAccountIdByProvider: {
            ...state.activeAccountIdByProvider,
            [provider]: accountId,
          },
        })),
      setActiveMarca: (marcaId) =>
        // Switching clients drops EVERY provider's account selection, not
        // just one — an account belongs to a client, so a client change
        // invalidates the whole map at once. (The old store cleared its
        // single id for the same reason.)
        set({ activeMarcaId: marcaId, activeAccountIdByProvider: {} }),
      clearSelection: () => set({ activeAccountIdByProvider: {}, activeMarcaId: null }),
    }),
    {
      name: "sw:active-account",
      version: 1,
      // Persist only the selection state — functions are re-created by zustand.
      partialize: (state) => ({
        activeAccountIdByProvider: state.activeAccountIdByProvider,
        activeMarcaId: state.activeMarcaId,
      }),
      /**
       * v0 → v1: the v0 payload carried a bare `activeAccountId` with no
       * record of which provider it had been chosen for. That attribution
       * is unrecoverable from localStorage alone, so the id is dropped
       * rather than guessed — guessing wrong reinstates the exact
       * cross-provider leak this version exists to remove. The cost is one
       * re-selection per browser on first load after deploy, and every page
       * already handles "no selection" by falling back to the org default.
       * `activeClientId` was never provider-specific, so it carries over.
       */
      migrate: (persisted, version) => {
        const legacy = (persisted ?? {}) as Partial<ActiveAccountState> & {
          activeAccountId?: string | null;
        };
        if (version === 0) {
          return {
            activeAccountIdByProvider: {},
            activeMarcaId: legacy.activeMarcaId ?? null,
          } as ActiveAccountState;
        }
        return legacy as ActiveAccountState;
      },
    },
  ),
);

/**
 * Read the account selected for `provider` — the supported read path.
 *
 * Returns null when nothing is selected for that provider, which every
 * caller already treats as "use the org default". Note it returns null for
 * a provider the user has never picked an account for even when another
 * provider has one selected: that is the entire point.
 */
export function useActiveAccountId(provider: string): string | null {
  return useActiveAccountStore((s) => s.activeAccountIdByProvider[provider] ?? null);
}
