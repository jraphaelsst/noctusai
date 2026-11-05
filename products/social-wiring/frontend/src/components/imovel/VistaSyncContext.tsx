/**
 * VistaSyncContext — when the Vista mirror of THIS imóvel was last synced.
 *
 * The detail page provides it once (`imovel.sincronizado_em`); every
 * mirror-sourced section reads it through `SectionCard`, so the freshness
 * shown beside the "Vista" marker is the same everywhere and no section has
 * to be handed a prop for it. → KB § PATTERNS/frontend/mirror-owned-overlay.md
 */
import { createContext, useContext } from "react";

const VistaSyncContext = createContext<string | null>(null);

export const VistaSyncProvider = VistaSyncContext.Provider;

export function useVistaSyncedAt(): string | null {
  return useContext(VistaSyncContext);
}
