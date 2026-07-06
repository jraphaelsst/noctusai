/**
 * AppReviewNotice — the honest "gated write" state.
 *
 * The backend never fakes success for a Meta write that requires Meta App
 * Review clearance (publish/comment/DM permissions not yet granted to this
 * app for this account) — it returns `{ requires_app_review: true, error }`
 * as a 200. This card is the ONE place that shape renders across every
 * write-gated subtab (Conteúdo, Comentários, DMs) so the posture stays
 * consistent: never a silent/fake success.
 *
 * Kept as its own small component (not inlined per-subtab) so Wave 4's
 * shared shell extraction can lift it unchanged.
 */
import { ShieldAlert } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function AppReviewNotice({ error }: { error?: string | null }) {
  return (
    <Card data-testid="meta-app-review-gate" className="border-dashed">
      <CardContent className="flex items-start gap-3 p-4 text-sm">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <div>
          <div className="font-medium">Requer Revisão do app Meta</div>
          <p className="text-muted-foreground">
            {error ??
              "Esta ação exige que o app Meta desta conexão passe pela Revisão do app (App Review) antes de ficar disponível para esta conta."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default AppReviewNotice;
