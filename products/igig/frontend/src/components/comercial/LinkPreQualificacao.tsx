/**
 * The shareable pré-qualificação link, with copy-to-clipboard (roadmap R2:
 * "Comercial contains only the pré-qualificação form link + the funnel").
 */
import { useState } from "react";
import { Link as LinkIcon } from "lucide-react";
import { Button } from "@noctusai/lib/design-system";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";

export function LinkPreQualificacao() {
  const { orgId, orgSource } = useEffectiveSSOContext();
  const [copiado, setCopiado] = useState(false);

  // The link names the EFFECTIVE org of this visit (multi-org S6): a member who
  // switched org shares THAT org's form, never the SSO token's. Until
  // `/api/me/access` answers, the token's org is only a stand-in — a link copied
  // then could route leads to the org the user just left, so none is shown.
  if (orgSource !== "access" || !orgId) return null;
  const url = `${window.location.origin}/pre-qualificacao/${orgId}`;

  return (
    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-card p-3 text-sm">
      <LinkIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">Formulário de pré-qualificação</p>
        <code className="block truncate text-foreground">{url}</code>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          // Clipboard access can be refused (insecure context, permissions);
          // the URL is on screen regardless, so a refusal degrades to
          // copy-by-hand rather than losing it.
          navigator.clipboard
            ?.writeText(url)
            .then(() => setCopiado(true))
            .catch(() => setCopiado(false));
        }}
      >
        {copiado ? "Copiado" : "Copiar"}
      </Button>
    </div>
  );
}
