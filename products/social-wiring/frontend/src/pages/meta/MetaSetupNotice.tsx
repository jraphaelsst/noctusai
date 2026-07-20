/**
 * MetaSetupNotice — the honest "this connection needs Meta setup" state.
 *
 * Sibling of `AppReviewNotice`, but for a different Meta-side gate: the app
 * lacks the PRODUCT/capability behind an endpoint (Graph code 3 —
 * "Application does not have the capability to make this API call"), which
 * the backend surfaces as `{ requires_setup: true, error }` (a 200). The
 * canonical case is the Instagram DMs tab when the Messenger /
 * Instagram-messaging product is not set up on the app: the Conversations
 * API returns code 3 even though `instagram_manage_messages` was granted.
 *
 * Kept distinct from `AppReviewNotice` because the REMEDY differs — this is
 * a dashboard configuration step (add/finish the product), not an App
 * Review submission — so the copy points the admin at setup, not review.
 * Never a silent empty state: an unset capability rendering as "no
 * conversations" would lie about why the list is empty.
 */
import { Settings2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function MetaSetupNotice({ error }: { error?: string | null }) {
  return (
    <Card data-testid="meta-setup-gate" className="border-dashed">
      <CardContent className="flex items-start gap-3 p-4 text-sm">
        <Settings2 className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <div>
          <div className="font-medium">Requer configuração no app Meta</div>
          <p className="text-muted-foreground">
            O app Meta desta conexão ainda não tem a capacidade de mensagens do
            Instagram ativada. Adicione o produto Messenger (com as configurações
            do Instagram) ao app e reconecte a conta para ver as conversas.
          </p>
          {error && (
            <p className="mt-1 text-xs text-muted-foreground/70">{error}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default MetaSetupNotice;
