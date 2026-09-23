/**
 * Integrações — where channel keys and tokens are set up.
 *
 * Three groups (wave-2 contract, Slice F):
 *   E-mail            SMTP (envio de orçamentos/automações) + Gmail (respostas)
 *   Fontes de lead    WhatsApp (WAHA) + Meta Lead Ads → leads no Comercial
 *   Publicação        the Módulo 5 social channels (below)
 *
 * The Gmail OAuth callback lands back here as `?gmail=ok|erro&motivo=`: a
 * toast says what happened (the `motivo` in plain pt-BR), the Gmail status is
 * refetched, and the params are cleared so a reload does not repeat the toast.
 *
 * The screen exists so credentials can be configured whenever the platform
 * apps are approved, without another code change: the publishing path already
 * reads whatever is stored here.
 *
 * Token inputs are write-only. The API never returns a stored token, so the
 * field always starts empty and a saved credential is represented by STATUS,
 * not by a masked value — a masked value implies it could be revealed, and
 * here it genuinely cannot.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, Link2Off, Plug, ShieldAlert } from "lucide-react";

import { GmailCard } from "@/components/integracoes/GmailCard";
import { MetaLeadsCard, WhatsappLeadsCard } from "@/components/integracoes/LeadSourceCards";
import { SmtpCard } from "@/components/integracoes/SmtpCard";
import type { Canal } from "@/hooks/useDistribuicao";
import { EMAIL_INTEGRACAO_KEY, GMAIL_MOTIVO_LABEL } from "@/hooks/useEmailIntegracao";
import {
  useConectarCanal,
  useDesconectarCanal,
  useIntegracoes,
  type IntegracaoStatus,
} from "@/hooks/useIntegracoes";

const CANAL_LABEL: Record<Canal, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
};

/** What an operator must obtain before a channel can publish. */
const CANAL_AJUDA: Record<Canal, string> = {
  instagram: "Meta Graph API — token de página com instagram_content_publish",
  facebook: "Meta Graph API — token de página com pages_manage_posts",
  tiktok: "TikTok for Business — access token com video.publish",
  linkedin: "LinkedIn Open Platform — token com w_organization_social",
};

function statusBadge(i: IntegracaoStatus): { texto: string; variante: BadgeVariant } {
  if (i.ultimo_erro) return { texto: "reconectar", variante: "destructive" };
  if (!i.conectado) return { texto: "não conectado", variante: "muted" };
  return { texto: i.origem === "env" ? "conectado (env)" : "conectado", variante: "default" };
}

function LinhaCanal({ integracao }: { integracao: IntegracaoStatus }) {
  const conectar = useConectarCanal();
  const desconectar = useDesconectarCanal();
  const [token, setToken] = useState("");
  const [conta, setConta] = useState(integracao.conta_externa ?? "");
  const badge = statusBadge(integracao);

  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Plug className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">
          {CANAL_LABEL[integracao.canal]}
        </span>
        <Badge variant={badge.variante}>{badge.texto}</Badge>
        {integracao.conta_externa && (
          <span className="text-xs text-muted-foreground">{integracao.conta_externa}</span>
        )}
        {integracao.conectado && integracao.origem === "org" && (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Desconectar ${CANAL_LABEL[integracao.canal]}`}
            onClick={() => desconectar.mutate(integracao.canal)}
          >
            <Link2Off className="h-4 w-4" />
          </Button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">{CANAL_AJUDA[integracao.canal]}</p>

      {integracao.ultimo_erro && (
        <p className="flex items-start gap-1 text-xs text-destructive">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {integracao.ultimo_erro}
        </p>
      )}

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!token.trim()) return;
          conectar.mutate(
            { canal: integracao.canal, token: token.trim(), conta_externa: conta.trim() || undefined },
            // Clear immediately on success — the token has no reason to stay
            // in component state once it is stored.
            { onSuccess: () => setToken("") },
          );
        }}
      >
        <Input
          type="password"
          aria-label={`Token ${CANAL_LABEL[integracao.canal]}`}
          placeholder={integracao.conectado ? "substituir token…" : "colar token…"}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="min-w-[200px] flex-1"
        />
        <Input
          aria-label={`Conta ${CANAL_LABEL[integracao.canal]}`}
          placeholder="@conta"
          value={conta}
          onChange={(e) => setConta(e.target.value)}
          className="min-w-[140px]"
        />
        <Button
          type="submit"
          disabled={!token.trim() || conectar.isPending || !integracao.cofre_configurado}
        >
          {integracao.conectado ? "Substituir" : "Conectar"}
        </Button>
      </form>

      {conectar.isError && (
        <p className="text-xs text-destructive">
          {/* The server's own message — a 409 says "não configurado", a
              revoked/invalid token says something else entirely, and this
              must never blame the wrong one. */}
          {conectar.error instanceof Error ? conectar.error.message : "Não foi possível salvar."}
        </p>
      )}
    </li>
  );
}

/** `?gmail=ok|erro&motivo=` → one toast, a Gmail refetch, then clean params. */
function useRetornoGmail() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const resultado = params.get("gmail");
  const motivo = params.get("motivo");
  useEffect(() => {
    if (!resultado) return;
    if (resultado === "ok") {
      toast.success("Gmail conectado.");
    } else {
      const detalhe = motivo ? GMAIL_MOTIVO_LABEL[motivo] ?? motivo : null;
      toast.error(detalhe ? `Não foi possível conectar o Gmail: ${detalhe}.` : "Não foi possível conectar o Gmail.");
    }
    void qc.invalidateQueries({ queryKey: EMAIL_INTEGRACAO_KEY });
    setParams(
      (atual) => {
        const prox = new URLSearchParams(atual);
        prox.delete("gmail");
        prox.delete("motivo");
        return prox;
      },
      { replace: true },
    );
  }, [resultado, motivo, qc, setParams]);
}

function Grupo({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</h2>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">{children}</div>
    </section>
  );
}

export default function Integracoes() {
  const { integracoes, loading, cofreConfigurado } = useIntegracoes();
  useRetornoGmail();

  return (
    <div className="mx-auto w-full min-w-0 max-w-full space-y-6 overflow-x-hidden p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Integrações</h1>
        <p className="text-sm text-muted-foreground">
          E-mail, fontes de lead e canais de publicação. Senhas e tokens são gravados criptografados e nunca são
          exibidos de volta.
        </p>
      </header>

      <Grupo titulo="E-mail">
        <SmtpCard />
        <GmailCard />
      </Grupo>

      <Grupo titulo="Fontes de lead">
        <WhatsappLeadsCard />
        <MetaLeadsCard />
      </Grupo>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Canais de publicação</h2>
        {/* Surfaced up front, not only after a failed connect attempt —
            `cofreConfigurado` is `null` until the list has loaded, so this
            never flashes on first render. */}
        {cofreConfigurado === false && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              Criptografia não configurada neste ambiente (IGIG_COFRE_KEY). Nenhum
              canal pode ser conectado até que o servidor seja configurado.
            </p>
          </div>
        )}

        <div className="rounded-lg border border-border bg-card p-4">
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <ul className="divide-y divide-border">
              {integracoes.map((i) => (
                <LinhaCanal key={i.canal} integracao={i} />
              ))}
            </ul>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          Enquanto um canal não estiver conectado, a publicação falha de forma
          explícita — nada é marcado como publicado sem confirmação da plataforma.
        </p>
      </section>
    </div>
  );
}
