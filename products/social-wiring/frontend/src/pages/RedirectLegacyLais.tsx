/**
 * RedirectLegacyLais -- permanent redirect for the pre-rename `/lais/*` URLs (the module was renamed Lais -> Julia,
 * owner order 2026-10-19). Bookmarks, notification links already delivered (`/lais/conversas/h/:id`) and the first
 * WhatsApp message of leads keep working; query string and hash are carried across.
 *
 * NOC-REMEDIATE[drop-lais-route-alias]: delete with the backend `LegacyLaisPathAlias` after one release.
 */
import { Navigate, useLocation } from "react-router-dom";

export function paraJulia(pathname: string): string {
  return pathname.replace(/^\/lais(?=\/|$)/, "/julia");
}

export default function RedirectLegacyLais() {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={{ pathname: paraJulia(pathname), search, hash }} replace />;
}
