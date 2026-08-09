/**
 * Integrações — where channel keys and tokens are set up (Módulo 5).
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
import { useState } from "react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, Link2Off, Plug } from "lucide-react";

import type { Canal } from "@/hooks/useDistribuicao";
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
        <Button type="submit" disabled={!token.trim() || conectar.isPending}>
          {integracao.conectado ? "Substituir" : "Conectar"}
        </Button>
      </form>

      {conectar.isError && (
        <p className="text-xs text-destructive">
          Não foi possível salvar. Sem IGIG_COFRE_KEY o token é recusado em vez de
          ser gravado em texto puro.
        </p>
      )}
    </li>
  );
}

export default function Integracoes() {
  const { integracoes, loading } = useIntegracoes();

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Integrações</h1>
        <p className="text-sm text-muted-foreground">
          Chaves e tokens dos canais. Tokens são gravados criptografados e nunca
          são exibidos de volta.
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-4">
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <ul className="divide-y divide-border">
            {integracoes.map((i) => (
              <LinhaCanal key={i.canal} integracao={i} />
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        Enquanto um canal não estiver conectado, a publicação falha de forma
        explícita — nada é marcado como publicado sem confirmação da plataforma.
      </p>
    </div>
  );
}
