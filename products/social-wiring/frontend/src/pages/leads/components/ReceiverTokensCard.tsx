/**
 * ReceiverTokensCard — the per-advertiser URLs pasted into Canal Pro.
 *
 * Grupo OLX issues one SECRET_KEY per CRM, not per advertiser, so nothing
 * in a delivery says whose lead it is. The URL does: each client gets a
 * distinct one, and the token in its path is what routes the lead to
 * their org.
 *
 * Three things this card has to get right, in the order they bite:
 *
 *   1. **The URL is shown exactly once.** It is never stored — only its
 *      digest is — so "I'll copy it later" is not a recoverable choice.
 *      The reveal says so, and stays open until dismissed rather than
 *      disappearing on the next render.
 *   2. **"Never received anything" is the failure that hides.** A URL
 *      pasted wrong into Canal Pro looks exactly like a quiet week. So
 *      `last_seen_at` is surfaced per row, and an unused URL is called
 *      out rather than left for someone to notice.
 *   3. **Revoking in the wrong order loses leads.** Canal Pro is edited
 *      by a human, so the old URL must keep working until the new one is
 *      pasted and confirmed. The revoke control says the order out loud.
 */
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Skeleton } from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  useMintReceiverToken,
  useReceiverTokens,
  useRevokeReceiverToken,
  type MintedReceiverToken,
  type ReceiverToken,
} from "@/hooks/useReceiverTokens";

function formatWhen(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("pt-BR");
}

export default function ReceiverTokensCard() {
  const { active, neverUsed, loading, isEmpty, isError, error, refetch } =
    useReceiverTokens("olx");
  const mint = useMintReceiverToken();
  const revoke = useRevokeReceiverToken();

  const [label, setLabel] = useState("");
  const [minted, setMinted] = useState<MintedReceiverToken | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("URL copiada — cole no Canal Pro do cliente.");
    } catch {
      toast.error("Não foi possível copiar. Selecione e copie manualmente.");
    }
  };

  const submitMint = async () => {
    const trimmed = label.trim();
    if (!trimmed) {
      toast.error("Dê um nome ao cliente para identificar esta URL depois.");
      return;
    }
    try {
      const result = await mint.mutateAsync({ provider: "olx", label: trimmed });
      setMinted(result);
      setLabel("");
    } catch {
      toast.error("Não foi possível gerar a URL. Tente novamente.");
    }
  };

  const submitRevoke = async (token: ReceiverToken) => {
    try {
      await revoke.mutateAsync(token.id);
      setConfirmingId(null);
      toast.success(`URL de ${token.label} revogada.`);
    } catch {
      toast.error("Não foi possível revogar. Tente novamente.");
    }
  };

  return (
    <div
      className="rounded-lg border border-border p-4 space-y-4"
      data-testid="receiver-tokens-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">URLs por cliente (Canal Pro)</h3>
          <p className="text-xs text-muted-foreground">
            Cada cliente recebe uma URL própria. É ela que identifica de quem é
            o lead — o Grupo OLX usa uma única chave para todo o CRM e não
            informa o anunciante.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
          data-testid="receiver-tokens-refresh"
          aria-label="Atualizar"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* The one-time reveal. Deliberately not a toast: a toast vanishes,
          and this value cannot be asked for again. */}
      {minted ? (
        <div
          className="space-y-2 rounded-md border border-amber-500/50 bg-amber-500/5 p-3"
          data-testid="receiver-token-reveal"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="text-sm">
              <p className="font-medium">
                Copie agora — esta URL não será mostrada de novo.
              </p>
              <p className="text-xs text-muted-foreground">
                Guardamos apenas um resumo dela. Se perder, gere outra e revogue
                esta.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <code
              className="flex-1 break-all rounded-md bg-muted px-2 py-1.5 text-xs"
              data-testid="receiver-token-url"
            >
              {minted.url}
            </code>
            <Button
              variant="outline"
              size="sm"
              onClick={() => copy(minted.url)}
              data-testid="receiver-token-copy"
            >
              <Copy className="mr-1 h-3.5 w-3.5" />
              Copiar
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMinted(null)}
            data-testid="receiver-token-dismiss"
          >
            Já copiei
          </Button>
        </div>
      ) : null}

      {/* Mint */}
      <div className="flex items-end gap-2">
        <div className="flex-1 space-y-1.5">
          <label
            className="text-xs font-medium text-muted-foreground"
            htmlFor="receiver-token-label"
          >
            Nome do cliente
          </label>
          <Input
            id="receiver-token-label"
            value={label}
            placeholder="Ex.: One Consultoria Imobiliária"
            onChange={(e) => setLabel(e.target.value)}
            data-testid="receiver-token-label-input"
          />
        </div>
        <Button
          onClick={submitMint}
          disabled={mint.isPending}
          data-testid="receiver-token-mint"
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          {mint.isPending ? "Gerando…" : "Gerar URL"}
        </Button>
      </div>

      {loading ? (
        <div className="space-y-2" data-testid="receiver-tokens-loading">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : isError ? (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          data-testid="receiver-tokens-error"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
          <div>
            <p className="font-medium">Não foi possível carregar as URLs.</p>
            <p className="text-xs text-muted-foreground">
              {(error as Error | null)?.message ?? "Tente novamente."}
            </p>
          </div>
        </div>
      ) : isEmpty ? (
        <div
          className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground"
          data-testid="receiver-tokens-empty"
        >
          Nenhuma URL gerada ainda. Gere uma por cliente e cole em Canal Pro →
          Configurações → Integrações → Leads → &quot;Receber leads no CRM&quot;.
        </div>
      ) : (
        <div className="space-y-3" data-testid="receiver-tokens-success">
          {neverUsed.length > 0 ? (
            <div
              className="flex items-start gap-2 rounded-md border border-amber-500/50 bg-amber-500/5 p-3 text-sm"
              data-testid="receiver-tokens-unused-banner"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
              <div>
                <p className="font-medium">
                  {neverUsed.length} URL(s) nunca receberam nada
                </p>
                <p className="text-xs text-muted-foreground">
                  Isso é esperado antes da homologação. Depois dela, costuma
                  significar que a URL foi colada errada no Canal Pro — o
                  sintoma é idêntico ao de um período sem leads.
                </p>
              </div>
            </div>
          ) : (
            <div
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="receiver-tokens-healthy"
            >
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Todas as URLs ativas já receberam leads.
            </div>
          )}

          <ul className="space-y-2" data-testid="receiver-tokens-list">
            {active.map((token) => (
              <li
                key={token.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-2.5 text-xs"
                data-testid={`receiver-token-${token.id}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{token.label}</p>
                  <p className="text-muted-foreground">
                    <span className="font-mono">{token.token_prefix}…</span>
                    {" · último lead: "}
                    {formatWhen(token.last_seen_at)}
                  </p>
                </div>

                {token.last_seen_at ? (
                  <Badge variant="default">Recebendo</Badge>
                ) : (
                  <Badge variant="secondary">Sem uso</Badge>
                )}

                {confirmingId === token.id ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground">
                      Já colou a nova URL no Canal Pro?
                    </span>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => submitRevoke(token)}
                      disabled={revoke.isPending}
                      data-testid={`receiver-token-revoke-confirm-${token.id}`}
                    >
                      Revogar
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmingId(null)}
                      data-testid={`receiver-token-revoke-cancel-${token.id}`}
                    >
                      Cancelar
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmingId(token.id)}
                    aria-label={`Revogar URL de ${token.label}`}
                    data-testid={`receiver-token-revoke-${token.id}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </li>
            ))}
          </ul>

          <p className="border-t border-dashed border-border pt-3 text-xs text-muted-foreground">
            Para trocar a URL de um cliente: gere a nova, cole no Canal Pro,
            confirme que voltou a receber e só então revogue a antiga. Revogar
            antes derruba todos os leads entregues no intervalo — o Grupo OLX
            não reenvia.
          </p>
        </div>
      )}
    </div>
  );
}
