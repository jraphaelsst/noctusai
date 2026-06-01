/**
 * AddAccountModal — add a credential account for a given provider.
 *
 * Layout:
 *   · If provider supports OAuth: primary "Connect via OAuth" button.
 *   · Below: collapsible "Or enter credentials manually" section built
 *     from providerConfig.manual_key_fields (BE-provided field list).
 *   · Tutorial link ("How do I get this?") when tutorial_url is set.
 *   · Loading / error / success states; success → toast + close modal.
 */
import { useState } from "react";
import { ExternalLink, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

import {
  useCreateAccount,
  useStartYouTubeOAuth,
  type IntegrationProvider,
} from "@/hooks/useIntegrationAccounts";

export interface AddAccountModalProps {
  provider: string;
  providerConfig: IntegrationProvider;
  onClose: () => void;
}

// Tutorial copy per provider (v1)
const TUTORIAL_COPY: Record<string, string> = {
  youtube:
    "Use the OAuth button — sign in to your YouTube account and grant upload permissions. " +
    "Multiple channels under one Google account are detected automatically.",
  n8n:
    "Get your API URL and API Key from your n8n instance: Settings → API.",
  meta: "Coming soon — Meta OAuth integration is under development.",
  google_drive: "Coming soon — Google Drive OAuth integration is under development.",
  gmail: "Coming soon — Gmail OAuth integration is under development.",
};

function tutorialCopy(provider: string): string {
  return TUTORIAL_COPY[provider.toLowerCase()] ?? "Contact support for setup instructions.";
}

export default function AddAccountModal({
  provider,
  providerConfig,
  onClose,
}: AddAccountModalProps) {
  const createMutation = useCreateAccount();
  const oauthMutation = useStartYouTubeOAuth();

  const [showManual, setShowManual] = useState(!providerConfig.oauth_supported);
  const [label, setLabel] = useState("");
  const [fields, setFields] = useState<Record<string, string>>(() =>
    Object.fromEntries(providerConfig.manual_key_fields.map((f) => [f.name, ""]))
  );

  // Only YouTube has a real OAuth flow in v1; other oauth_supported providers
  // show a "coming soon" OAuth path while still offering manual entry.
  const isYouTube = provider.toLowerCase() === "youtube";
  const oauthReady = providerConfig.oauth_supported && isYouTube;
  const oauthComingSoon = providerConfig.oauth_supported && !isYouTube;

  function setField(fieldName: string, value: string) {
    setFields((prev) => ({ ...prev, [fieldName]: value }));
  }

  async function handleOAuth() {
    if (!oauthReady) return;
    try {
      await oauthMutation.mutateAsync();
      // window.location.assign fires in mutation onSuccess; toast for feedback
      toast.info("Redirecting to Google sign-in...");
    } catch (err: any) {
      toast.error("Falha ao iniciar OAuth", {
        description: err?.message ?? "Tente novamente",
      });
    }
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) {
      toast.error("Informe um nome para a conta");
      return;
    }
    const missing = providerConfig.manual_key_fields.filter(
      (f) => !fields[f.name]?.trim()
    );
    if (missing.length > 0) {
      toast.error(`Preencha: ${missing.map((f) => f.label).join(", ")}`);
      return;
    }
    try {
      await createMutation.mutateAsync({
        provider,
        account_label: label.trim(),
        credential: fields,
      });
      toast.success("Conta adicionada com sucesso");
      onClose();
    } catch (err: any) {
      toast.error("Erro ao adicionar conta", {
        description: err?.message ?? "Tente novamente",
      });
    }
  }

  const saving = createMutation.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            Adicionar conta — {providerConfig.display_name}
          </DialogTitle>
          <DialogDescription>
            {tutorialCopy(provider)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* OAuth section */}
          {providerConfig.oauth_supported && (
            <div className="space-y-2">
              {oauthReady && (
                <Button
                  className="w-full"
                  onClick={handleOAuth}
                  disabled={oauthMutation.isPending}
                >
                  {oauthMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Conectar via OAuth
                </Button>
              )}
              {oauthComingSoon && (
                <Button className="w-full" disabled variant="secondary">
                  Conectar via OAuth (em breve)
                </Button>
              )}
            </div>
          )}

          {/* Manual section toggle */}
          {providerConfig.oauth_supported && providerConfig.manual_key_fields.length > 0 && (
            <div>
              <Separator />
              <Button
                variant="ghost"
                size="sm"
                className="mt-3 text-muted-foreground"
                onClick={() => setShowManual((v) => !v)}
                type="button"
              >
                {showManual ? "Ocultar credenciais manuais" : "Ou inserir credenciais manualmente"}
              </Button>
            </div>
          )}

          {/* Manual form */}
          {showManual && providerConfig.manual_key_fields.length > 0 && (
            <form onSubmit={handleManualSubmit} className="space-y-3">
              <div className="grid gap-1.5">
                <Label htmlFor="acc-label">Nome da conta *</Label>
                <Input
                  id="acc-label"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Ex: Canal principal"
                  disabled={saving}
                />
              </div>
              {providerConfig.manual_key_fields.map((field) => (
                <div key={field.name} className="grid gap-1.5">
                  <Label htmlFor={`acc-${field.name}`}>{field.label} *</Label>
                  <Input
                    id={`acc-${field.name}`}
                    type={field.type}
                    value={fields[field.name] ?? ""}
                    onChange={(e) => setField(field.name, e.target.value)}
                    placeholder={field.placeholder}
                    disabled={saving}
                    autoComplete={field.type === "password" ? "off" : undefined}
                  />
                </div>
              ))}
              {providerConfig.tutorial_url && (
                <a
                  href={providerConfig.tutorial_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline"
                >
                  Como obter essas credenciais?
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={saving}>
                  {saving ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="mr-2 h-4 w-4" />
                  )}
                  Adicionar
                </Button>
              </DialogFooter>
            </form>
          )}

          {/* No-fields provider (OAuth only, no manual form) */}
          {showManual && providerConfig.manual_key_fields.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Este provedor so suporta autenticacao via OAuth.
            </p>
          )}
        </div>

        {/* Footer for OAuth-only path (no form) */}
        {!showManual && (
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              Cancelar
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
