/**
 * RedirectToLaisConversas — permanent redirect for the retired `/whatsapp-chat`
 * route (WhatsApp moved into the "Lais" nav group, owner decision 2026-10-13).
 *
 * Mirrors `RedirectToMeta.tsx`, but carries the query string + hash across so
 * any deep-link keeps its parameters. Connection pre-selection itself rides on
 * `useActiveAccountStore` (set by the WhatsApp IntegrationCard click BEFORE it
 * navigates here), so it survives this hop untouched.
 */
import { Navigate, useLocation } from "react-router-dom";

import { LAIS_PAGES } from "@/nav/lais";

export default function RedirectToLaisConversas() {
  const { search, hash } = useLocation();
  return (
    <Navigate to={{ pathname: LAIS_PAGES.conversas.href, search, hash }} replace />
  );
}
