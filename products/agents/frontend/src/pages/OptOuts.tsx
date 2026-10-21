/**
 * Opt-outs -- `/opt-outs`: leads que pediram para não ser mais contatados.
 *
 * Cada registro diz quando, qual lead, quem encerrou (agente / operador / integração), por quê, o que o lead
 * escreveu, quantas conversas foram encerradas e se o aviso ao dono saiu. Aviso que FALHOU aparece em destaque,
 * com o erro, e um admin pode reenviá-lo. `?evento=<id>` (o link da notificação) destaca o registro.
 */
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, BellOff, CheckCircle2, Clock } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState } from "@noctusai/lib/design-system";
import type { OptOutEvento } from "@/api/studio/types-julia";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useOptOuts, useReenviarNotificacao } from "@/hooks/useOptOuts";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { optOutData, optOutMotivo, optOutQuem } from "@/lib/optOut";
import { cn } from "@/lib/utils";

function NotificacaoStatus({ ev }: { ev: OptOutEvento }) {
  if (ev.notificacao_status === "enviada") {
    return (
      <Badge variant="muted" data-testid={`optout-status-${ev.id}`}>
        <CheckCircle2 className="mr-1 inline h-3 w-3" /> Dono avisado{ev.notificado_em ? ` em ${optOutData(ev.notificado_em)}` : ""}
      </Badge>
    );
  }
  if (ev.notificacao_status === "pendente") {
    return (
      <Badge variant="outline" data-testid={`optout-status-${ev.id}`}>
        <Clock className="mr-1 inline h-3 w-3" /> Aviso pendente
      </Badge>
    );
  }
  return (
    <Badge variant="default" className="bg-destructive text-destructive-foreground" data-testid={`optout-status-${ev.id}`}>
      <AlertTriangle className="mr-1 inline h-3 w-3" /> Aviso falhou
    </Badge>
  );
}

function Registro({ ev, destaque, isAdmin }: { ev: OptOutEvento; destaque: boolean; isAdmin: boolean }) {
  const reenviar = useReenviarNotificacao();
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (destaque) ref.current?.scrollIntoView?.({ block: "center" });
  }, [destaque]);

  async function onReenviar() {
    try {
      const r = await reenviar.mutateAsync(ev.id);
      if (r.notificacao_status === "enviada") toast.success("Notificação reenviada.");
      else toast.error(`O reenvio falhou: ${r.notificacao_erro ?? "erro desconhecido"}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const falhou = ev.notificacao_status === "falhou";
  const precisaReenvio = falhou || ev.notificacao_status === "pendente";
  return (
    <li
      ref={ref}
      id={`optout-${ev.id}`}
      data-testid={`optout-${ev.id}`}
      data-destaque={destaque ? "true" : undefined}
      className={cn(
        "space-y-2 rounded-lg border bg-card p-4",
        falhou ? "border-destructive/60" : "border-border",
        destaque && "ring-2 ring-primary",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">{ev.lead_nome ?? ev.lead_ref ?? "Lead sem nome"}</h2>
        {ev.lead_telefone && <span className="text-xs text-muted-foreground">{ev.lead_telefone}</span>}
        <span className="ml-auto text-xs text-muted-foreground">{optOutData(ev.em)}</span>
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted-foreground">Quem encerrou</dt>
        <dd data-testid={`optout-quem-${ev.id}`}>{optOutQuem(ev)}</dd>
        <dt className="text-muted-foreground">Motivo</dt>
        <dd data-testid={`optout-motivo-${ev.id}`}>{optOutMotivo(ev)}</dd>
        <dt className="text-muted-foreground">O que o lead escreveu</dt>
        <dd className="whitespace-pre-wrap" data-testid={`optout-mensagem-${ev.id}`}>
          {ev.mensagem_lead ? `“${ev.mensagem_lead}”` : "—"}
        </dd>
        <dt className="text-muted-foreground">Conversas encerradas</dt>
        <dd data-testid={`optout-encerradas-${ev.id}`}>{ev.participantes_encerrados}</dd>
      </dl>
      <div className="flex flex-wrap items-center gap-2">
        <NotificacaoStatus ev={ev} />
        {precisaReenvio && isAdmin && (
          <Button size="sm" variant="outline" disabled={reenviar.isPending} onClick={onReenviar} data-testid={`optout-reenviar-${ev.id}`}>
            Reenviar notificação
          </Button>
        )}
      </div>
      {falhou && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert" data-testid={`optout-erro-${ev.id}`}>
          O dono NÃO foi avisado. {ev.notificacao_erro ? `Erro: ${ev.notificacao_erro}` : "Erro não informado."}
        </p>
      )}
    </li>
  );
}

export default function OptOuts() {
  const [params] = useSearchParams();
  const destaque = params.get("evento");
  const isAdmin = useIsAdmin();
  const lista = useOptOuts();

  return (
    <div className="space-y-4" data-testid="optouts-page">
      <header className="flex items-center gap-2">
        <BellOff className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-lg font-semibold">Opt-outs</h1>
      </header>
      <p className="text-sm text-muted-foreground">
        Leads que pediram para não ser mais contatados. Nenhum agente volta a falar com eles.
      </p>
      {lista.showSkeleton ? (
        <StudioLoading rows={4} testId="optouts-skeleton" />
      ) : lista.isError && !lista.items ? (
        <div data-testid="optouts-error">
          <StudioError error={lista.error} onRetry={lista.refetch} />
        </div>
      ) : !lista.items || lista.items.length === 0 ? (
        <div data-testid="optouts-empty">
          <EmptyState message="Nenhum lead pediu para parar de ser contatado." />
        </div>
      ) : (
        <>
          {lista.isRefreshing && <p className="text-xs text-muted-foreground">Atualizando…</p>}
          <ol className="space-y-3" data-testid="optouts-lista">
            {lista.items.map((ev) => (
              <Registro key={ev.id} ev={ev} destaque={ev.id === destaque} isAdmin={isAdmin} />
            ))}
          </ol>
          {lista.hasMore && (
            <Button variant="outline" disabled={lista.isFetchingMore} onClick={lista.fetchMore} data-testid="optouts-mais">
              {lista.isFetchingMore ? "Carregando…" : "Carregar mais"}
            </Button>
          )}
        </>
      )}
    </div>
  );
}
