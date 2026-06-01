/**
 * useActiveAccount — lightweight Zustand store holding the active account/client
 * selection for YouTube data views (Dashboard, Videos, Upload).
 *
 * Persisted to localStorage so the selection survives navigation between the
 * YouTube tab, Dashboard and Videos pages within the same session.
 *
 * Selecting a client narrows the accounts visible in the switcher to that
 * client's accounts. Selecting an account pins YT data requests to that account.
 * Clearing (null) falls back to the org default.
 *
 * Usage:
 *   const { activeAccountId, activeClientId, setActiveAccount, setActiveClient } =
 *     useActiveAccountStore();
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ActiveAccountState {
  /** The currently selected integration account UUID; null = org default. */
  activeAccountId: string | null;
  /** The currently selected client UUID; null = all clients / unfiltered. */
  activeClientId: string | null;
  setActiveAccount: (accountId: string | null) => void;
  setActiveClient: (clientId: string | null) => void;
  /** Convenience: clear both selections at once. */
  clearSelection: () => void;
}

export const useActiveAccountStore = create<ActiveAccountState>()(
  persist(
    (set) => ({
      activeAccountId: null,
      activeClientId: null,
      setActiveAccount: (accountId) => set({ activeAccountId: accountId }),
      setActiveClient: (clientId) =>
        // When switching clients reset the account selection to avoid
        // pointing at an account from a different client.
        set({ activeClientId: clientId, activeAccountId: null }),
      clearSelection: () => set({ activeAccountId: null, activeClientId: null }),
    }),
    {
      name: "sw:active-account",
      // Persist only the selection IDs — functions are re-created by zustand.
      partialize: (state) => ({
        activeAccountId: state.activeAccountId,
        activeClientId: state.activeClientId,
      }),
    },
  ),
);
