/**
 * ImovelHistoricoCard — "Histórico" of an imóvel: Vista changes, approvals, sends to Vista, prices and notes on ONE
 * thread (owner 2026-11-04). The thread is the SEED `Timeline` organ (same adapter pattern as the lead card's
 * `components/card/Timeline.tsx`): per-kind renderers register a one-line summary; nothing is forked.
 *
 * The seed row is presentational (icon + summary), so the things a row needs that a sentence cannot carry — the
 * "Aprovar" / "Manter Vista" buttons of a PENDING approval and the "Ver conversa" link — live in a strip above the
 * thread, built from the same data. Buttons are org-admin (UX only; the server enforces); a refusal is drawn on the
 * item, never silent. Vista wins: nothing here alerts anyone.
 *
 * States: loading (seed skeleton) · empty (seed) · error with retry (`QueryErrorState`, never mistaken for empty) · data.
 */
import { ArrowRightLeft, CloudUpload, History, Loader2, MessageSquare, Tag } from "lucide-react";

import { isOrgAdmin } from "@noctusai/lib";
import { DEFAULT_TIMELINE_RENDERERS, QueryErrorState, Timeline } from "@noctusai/lib/components";
import type { TimelineEntry, TimelineRenderers } from "@noctusai/lib/components";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useImovelHistorico,
  useResolverAprovacao,
  type HistoricoItem,
  type HistoricoPayload,
} from "@/hooks/useImovelHistorico";
import { mensagemErroServidor } from "@/lib/erroServidor";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function valor(campo: string | null | undefined, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "sim" : "não";
  if (typeof v === "number" && campo?.startsWith("valor_")) return brl.format(v);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function mudanca(p: HistoricoPayload): string {
  const nome = p.rotulo || p.campo || "campo";
  return `${nome}: ${valor(p.campo, p.de)} → ${valor(p.campo, p.para)}`;
}

const pay = (e: { payload?: HistoricoPayload }): HistoricoPayload => e.payload ?? {};

const SUMMARY: Record<string, (p: HistoricoPayload) => string> = {
  vista: (p) => (p.acao === "vista_prevaleceu" ? `Vista prevaleceu — ${mudanca(p)}` : `Vista atualizou — ${mudanca(p)}`),
  aprovacao: (p) => {
    if (p.acao === "aprovacao_pendente" && p.status === "pendente") return `Aprovação pendente — ${mudanca(p)}`;
    if (p.status === "recusada") return `Aprovação recusada (Vista mantido) — ${mudanca(p)}`;
    return `Aprovação decidida (${p.status === "pendente" ? "aberta" : "aprovada"}) — ${mudanca(p)}`;
  },
  vista_envio: (p) =>
    p.acao === "envio_vista_falhou"
      ? `Falha ao enviar ao Vista — ${mudanca(p)}${p.detalhe ? ` (${p.detalhe})` : ""}`
      : `Enviado ao Vista — ${mudanca(p)}${p.detalhe ? ` (${p.detalhe})` : ""}`,
  alteracao: (p) => `Alteração — ${mudanca(p)}`,
  preco: (p) => `Preço — ${mudanca(p)}`,
};

export const IMOVEL_HISTORICO_RENDERERS: TimelineRenderers = {
  ...DEFAULT_TIMELINE_RENDERERS,
  vista: { icon: ArrowRightLeft, summary: (e) => SUMMARY.vista(pay(e)) },
  aprovacao: { icon: History, summary: (e) => SUMMARY.aprovacao(pay(e)) },
  vista_envio: { icon: CloudUpload, summary: (e) => SUMMARY.vista_envio(pay(e)) },
  alteracao: { icon: History, summary: (e) => SUMMARY.alteracao(pay(e)) },
  preco: { icon: Tag, summary: (e) => SUMMARY.preco(pay(e)) },
};

/** The seed row reads `ator.nome.trim()` and the nota renderer reads `corpo` — normalise both from the API shape. */
export function paraTimeline(items: HistoricoItem[]): TimelineEntry[] {
  return items.map((i) => {
    const base: Record<string, unknown> = { ...i, ator: i.ator?.nome ? { nome: i.ator.nome } : null };
    if (i.kind === "nota") {
      base.corpo = i.payload?.corpo ?? "";
      base.deleted_at = null;
    }
    return base as unknown as TimelineEntry;
  });
}

const pendente = (i: HistoricoItem) =>
  i.kind === "aprovacao" && i.payload?.status === "pendente" && !!i.payload?.divergencia_id;

function AprovacaoPendente({ item, codigo, admin }: { item: HistoricoItem; codigo: string; admin: boolean }) {
  const resolver = useResolverAprovacao(codigo);
  const p = item.payload;
  const ocupado = resolver.isPending;
  const decidir = (escolha: "aprovar" | "recusar") =>
    resolver.mutate({ historicoId: item.id, divergenciaId: p.divergencia_id as string, escolha });

  return (
    <li className="space-y-2 py-3" data-testid={`aprovacao-${item.id}`}>
      <p className="text-sm font-medium">{mudanca(p)}</p>
      <p className="text-xs text-muted-foreground">
        O proprietário confirmou um valor diferente do Vista. Por enquanto o Vista prevalece; aprovar envia o nosso valor ao Vista
        (se a edição no Vista estiver ligada) ou registra para atualizar manualmente.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {p.conversa?.url && (
          <a
            href={p.conversa.url}
            className="inline-flex items-center gap-1 text-xs underline underline-offset-2 hover:text-foreground"
            data-testid={`aprovacao-${item.id}-conversa`}
          >
            <MessageSquare className="h-3 w-3" />
            Ver conversa
          </a>
        )}
        {admin ? (
          <>
            <Button size="sm" disabled={ocupado} onClick={() => decidir("aprovar")} data-testid={`aprovacao-${item.id}-aprovar`}>
              {ocupado && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Aprovar
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={ocupado}
              onClick={() => decidir("recusar")}
              data-testid={`aprovacao-${item.id}-manter-vista`}
            >
              Manter Vista
            </Button>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">Um administrador da organização decide.</span>
        )}
      </div>
      {resolver.isError && (
        <p className="text-sm text-destructive" role="alert" data-testid={`aprovacao-${item.id}-erro`}>
          {mensagemErroServidor(resolver.error, "Não foi possível registrar a decisão.")}
        </p>
      )}
    </li>
  );
}

export function ImovelHistoricoCard({ codigo }: { codigo: string }) {
  const h = useImovelHistorico(codigo);
  const admin = isOrgAdmin(useEffectiveSSOContext());
  const pendentes = h.items.filter(pendente);

  return (
    <Card id="imovel-historico" data-testid="imovel-historico">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4" />
          Histórico
          {pendentes.length > 0 && (
            <Badge data-testid="imovel-historico-pendentes">{pendentes.length} pendente(s)</Badge>
          )}
          {h.isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" data-testid="imovel-historico-refreshing" />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Tudo o que muda neste imóvel fica aqui. O Vista prevalece e ninguém é avisado por WhatsApp ou e-mail.
        </p>
        {h.isError && h.items.length === 0 ? (
          <QueryErrorState query={{ ...h, data: undefined }} title="Não foi possível carregar o histórico do imóvel." data-testid="imovel-historico-erro" />
        ) : (
          <>
            {pendentes.length > 0 && (
              <ul className="divide-y rounded-md border px-3" data-testid="imovel-historico-aprovacoes">
                {pendentes.map((i) => (
                  <AprovacaoPendente key={i.id} item={i} codigo={codigo} admin={admin} />
                ))}
              </ul>
            )}
            <Timeline
              entries={paraTimeline(h.items)}
              loading={h.showSkeleton}
              error={null}
              hasMore={!!h.hasNextPage}
              loadingMore={h.isFetchingNextPage}
              onLoadMore={() => void h.fetchNextPage()}
              renderers={IMOVEL_HISTORICO_RENDERERS}
              testId="imovel-historico-timeline"
            />
            {h.isError && h.items.length > 0 && (
              <p className="text-xs text-destructive" role="alert" data-testid="imovel-historico-erro-mais">
                Não foi possível atualizar o histórico. Mostrando o que já foi carregado.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
