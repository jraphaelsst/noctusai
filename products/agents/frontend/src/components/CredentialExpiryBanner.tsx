/**
 * In-app 30-day expiry warning (contract D1 deferral) — shown on the
 * dashboard to platform admins when any credential needs attention. The
 * daily `agents_credential_maintenance` job sends the matching bell
 * notification; this banner is the always-visible half.
 *
 * Only ASKS when the user looks like a platform admin (UX hint), and renders
 * nothing on any error — a 403 here is an answer, not a failure to surface.
 */
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useCredentials } from "@/hooks/useCredentials";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";

export function CredentialExpiryBanner() {
  const isPlatformAdmin = useIsPlatformAdmin();
  const { data } = useCredentials({ enabled: isPlatformAdmin });
  const flagged = data?.items.filter((c) => c.severity !== "info") ?? [];
  if (!isPlatformAdmin || flagged.length === 0) return null;

  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700"
      role="status"
      data-testid="credential-expiry-banner"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <div className="flex-1">
        <p className="font-medium">Credenciais precisam de atenção</p>
        <ul className="text-xs">
          {flagged.map((c) => (
            <li key={c.name}>
              {c.label}: {c.warnings[0] ?? "verifique"}
            </li>
          ))}
        </ul>
      </div>
      <Link to="/credenciais" className="text-xs font-medium underline">
        Abrir
      </Link>
    </div>
  );
}
