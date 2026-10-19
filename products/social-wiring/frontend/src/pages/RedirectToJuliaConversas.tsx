/**
 * RedirectToJuliaConversas — permanent redirect for the retired `/whatsapp-chat`
 * route (WhatsApp moved into the "Julia" nav group, owner decision 2026-10-13).
 *
 * Mirrors `RedirectToMeta.tsx`, but carries the query string + hash across so
 * any deep-link keeps its parameters. Connection pre-selection itself rides on
 * `useActiveAccountStore` (set by the WhatsApp IntegrationCard click BEFORE it
 * navigates here), so it survives this hop untouched.
 */
import { Navigate, useLocation } from "react-router-dom";

import { JULIA_PAGES } from "@/nav/julia";

export default function RedirectToJuliaConversas() {
  const { search, hash } = useLocation();
  return (
    <Navigate to={{ pathname: JULIA_PAGES.conversas.href, search, hash }} replace />
  );
}
