/** Julia › Opt-outs › histórico: newest-first opt-out + reactivation records of the org's leads, straight from agents. */
import { useEffect, useRef, useState } from "react";
import { AlertCircle, BellRing, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  formatarDataHora, useOptOuts, useReativarLead, useRenotificarOptOut, type OptOutEvento,
} from "@/hooks/useJuliaOptOuts";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { MotivoDialog } from "./MotivoDialog";

export function quemFez(e: OptOutEvento): string {
  if (e.origem === "agente") return e.agent_nome ? `Agente (${e.agent_nome})` : "Agente";
  if (e.origem === "operador") return e.ator_nome ? `Operador: ${e.ator_nome}` : "Operador";
  if (e.origem === "integracao") return "Integração";
  return e.ator_nome ?? "—";
}

export function OptOutHistorico({ eventoDestaque }: { eventoDestaque: string | null }) {
  const q = useOptOuts();
  const isAdmin = useIsOrgAdmin();
  const renotificar = useRenotificarOptOut();
  const reativar = useReativarLead();
  const [alvo, setAlvo] = useState<OptOutEvento | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const destaqueRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    destaqueRef.current?.scrollIntoView?.({ block: "center" });
  }, [eventoDestaque, q.items.length]);

  if (q.showSkeleton) return <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="optouts-skeleton" />;
  if (q.isError && !q.data) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="optouts-erro">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm">{mensagemErroServidor(q.error, "Não foi possível carregar o histórico de opt-outs.")}</p>
        <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
      </div>
    );
  }
  if (q.items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-16 text-center" data-testid="optouts-vazio">
        <ShieldCheck className="h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Nenhum lead pediu para não ser contatado.</p>
      </div>
    );
  }

  function reenviar(e: OptOutEvento) {
    renotificar.mutate({ eventoId: e.id }, {
      onSuccess: () => toast.success("Notificação reenviada."),
      onError: (err) => toast.error(mensagemErroServidor(err, "Não foi possível reenviar a notificação.")),
    });
  }
  function confirmarReativacao(motivo: string) {
    if (!alvo) return;
    setErro(null);
    reativar.mutate({ contatoId: alvo.lead_ref, motivo }, {
      onSuccess: () => { setAlvo(null); toast.success("Atendimento reativado."); },
      onError: (err) => setErro(mensagemErroServidor(err, "Não foi possível reativar o atendimento.")),
    });
  }

  return (
    <div className="space-y-3">
      {q.isRefreshing && (
        <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="optouts-refreshing">
          <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
        </span>
      )}
      <ul className="space-y-2" data-testid="optouts-lista">
        {q.items.map((e) => {
          const destacado = e.id === eventoDestaque;
          const falhou = e.notificacao_status === "falhou";
          return (
            <li
              key={e.id} ref={destacado ? destaqueRef : undefined} data-testid="optout-item" data-tipo={e.tipo}
              data-destacado={destacado ? "true" : "false"}
              className={`rounded-lg border p-3 ${destacado ? "ring-2 ring-primary" : ""} ${falhou ? "border-destructive/40 bg-danger-light" : ""}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {e.tipo === "opt_out" ? <ShieldOff className="h-4 w-4 text-warning-foreground" /> : <ShieldCheck className="h-4 w-4 text-success" />}
                    {e.tipo === "opt_out" ? "Pediu para não ser contatado" : "Atendimento reativado"}
                    {e.ativo === true && <span className="rounded-full bg-warning-light px-2 py-0.5 text-xs text-warning-foreground" data-testid="optout-ativo">opt-out ativo</span>}
                  </div>
                  <div className="text-sm">{e.lead_nome || "Lead sem nome"} · {e.lead_telefone || "sem telefone"}</div>
                  <div className="text-xs text-muted-foreground">{formatarDataHora(e.em)} · {quemFez(e)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {e.tipo === "opt_out" && e.ativo === true && isAdmin && (
                    <Button size="sm" variant="outline" onClick={() => { setErro(null); setAlvo(e); }} data-testid="optout-reativar">
                      Reativar atendimento
                    </Button>
                  )}
                  {falhou && isAdmin && (
                    <Button size="sm" variant="outline" disabled={renotificar.isPending} onClick={() => reenviar(e)} data-testid="optout-reenviar">
                      <BellRing className="mr-1 h-4 w-4" /> Reenviar notificação
                    </Button>
                  )}
                </div>
              </div>
              <dl className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
                <div><dt className="text-xs text-muted-foreground">Motivo</dt><dd>{e.motivo || "—"}</dd></div>
                {e.tipo === "opt_out" && <div><dt className="text-xs text-muted-foreground">Mensagem do lead</dt><dd>{e.mensagem_lead || "—"}</dd></div>}
                {e.tipo === "opt_out" && <div><dt className="text-xs text-muted-foreground">Conversas encerradas</dt><dd>{e.participantes_encerrados}</dd></div>}
                <div>
                  <dt className="text-xs text-muted-foreground">Notificação</dt>
                  <dd className={falhou ? "font-medium text-destructive" : ""} data-testid="optout-notificacao">
                    {e.notificacao_status === "enviada" ? `Enviada${e.notificado_em ? ` em ${formatarDataHora(e.notificado_em)}` : ""}`
                      : e.notificacao_status === "pendente" ? "Pendente" : "Falhou"}
                    {falhou && e.notificacao_erro && <span className="block text-xs">{e.notificacao_erro}</span>}
                  </dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ul>
      {q.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" size="sm" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()} data-testid="optouts-mais">
            {q.isFetchingNextPage && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} Carregar mais
          </Button>
        </div>
      )}
      <MotivoDialog
        aberto={alvo !== null} titulo="Reativar atendimento"
        descricao={`O lead ${alvo?.lead_nome ?? ""} volta para o fluxo dos agentes e poderá ser contatado novamente. Informe por que a reativação é legítima (ex.: o lead pediu para voltar).`}
        confirmar="Reativar atendimento" pendente={reativar.isPending} erro={erro}
        onConfirmar={confirmarReativacao} onFechar={() => setAlvo(null)}
      />
    </div>
  );
}
