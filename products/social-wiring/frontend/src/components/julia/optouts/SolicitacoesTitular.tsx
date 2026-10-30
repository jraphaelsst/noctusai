/** Julia › Opt-outs › solicitações de dados: LGPD requests Julia registered for a human. Admins decide; nothing is automatic. */
import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, ScrollText } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  ROTULO_STATUS_SOLICITACAO, ROTULO_TIPO_SOLICITACAO, formatarDataHora, useDecidirSolicitacao, useSolicitacoes,
  type PrazoSituacao, type Solicitacao, type StatusSolicitacao,
} from "@/hooks/useJuliaOptOuts";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { MotivoDialog } from "./MotivoDialog";

const PRAZO: Record<PrazoSituacao, { rotulo: string; classe: string }> = {
  vencida: { rotulo: "Prazo vencido", classe: "bg-danger-light text-destructive" },
  vence_em_breve: { rotulo: "Vence em até 3 dias", classe: "bg-warning-light text-warning-foreground" },
  no_prazo: { rotulo: "No prazo", classe: "bg-muted text-muted-foreground" },
  encerrada: { rotulo: "Encerrada", classe: "bg-muted text-muted-foreground" },
};
const FILTROS: (StatusSolicitacao | "")[] = ["", "aberta", "em_analise", "atendida", "negada", "cancelada"];
const DECISOES: { status: StatusSolicitacao; rotulo: string }[] = [
  { status: "em_analise", rotulo: "Em análise" },
  { status: "atendida", rotulo: "Marcar atendida" },
  { status: "negada", rotulo: "Negar" },
  { status: "cancelada", rotulo: "Cancelar" },
];

export function SolicitacoesTitular({ destaque }: { destaque: string | null }) {
  const [status, setStatus] = useState<StatusSolicitacao | "">("");
  const [page, setPage] = useState(1);
  const q = useSolicitacoes(status, page);
  const isAdmin = useIsOrgAdmin();
  const decidir = useDecidirSolicitacao();
  const [negando, setNegando] = useState<Solicitacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const destaqueRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => { destaqueRef.current?.scrollIntoView?.({ block: "center" }); }, [destaque, q.data]);

  const itens = q.data?.items ?? [];
  const total = q.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / 20));

  function mover(s: Solicitacao, novo: StatusSolicitacao, motivo?: string) {
    setErro(null);
    decidir.mutate({ id: s.id, status: novo, motivo }, {
      onSuccess: () => { setNegando(null); toast.success("Solicitação atualizada."); },
      onError: (e) => {
        const msg = mensagemErroServidor(e, "Não foi possível atualizar a solicitação.");
        if (novo === "negada") setErro(msg); else toast.error(msg);
      },
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="sol-status" className="text-sm text-muted-foreground">Status</label>
        <select
          id="sol-status" className="h-8 rounded-md border bg-background px-2 text-sm" value={status}
          onChange={(e) => { setStatus(e.target.value as StatusSolicitacao | ""); setPage(1); }}
        >
          {FILTROS.map((f) => <option key={f} value={f}>{f ? ROTULO_STATUS_SOLICITACAO[f] : "Todos"}</option>)}
        </select>
        {q.isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" data-testid="sol-refreshing" />}
      </div>

      {q.showSkeleton ? (
        <div className="h-48 animate-pulse rounded-lg bg-muted" data-testid="sol-skeleton" />
      ) : q.isError && !q.data ? (
        <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground" data-testid="sol-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">{mensagemErroServidor(q.error, "Não foi possível carregar as solicitações.")}</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : itens.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-12 text-center" data-testid="sol-vazio">
          <ScrollText className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhuma solicitação de dados.</p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="sol-lista">
          {itens.map((s) => {
            const prazo = PRAZO[s.prazo_situacao];
            const urgente = s.prazo_situacao === "vencida" || s.prazo_situacao === "vence_em_breve";
            return (
              <li
                key={s.id} ref={s.id === destaque ? destaqueRef : undefined} data-testid="sol-item" data-prazo={s.prazo_situacao}
                className={`rounded-lg border p-3 ${s.id === destaque ? "ring-2 ring-primary" : ""} ${s.prazo_situacao === "vencida" ? "border-destructive/40 bg-danger-light" : urgente ? "border-warning/40 bg-warning-light" : ""}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium">{ROTULO_TIPO_SOLICITACAO[s.tipo]}</div>
                    <div className="text-xs text-muted-foreground">Recebida em {formatarDataHora(s.recebida_em)}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${prazo.classe}`} data-testid="sol-prazo">{prazo.rotulo}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{ROTULO_STATUS_SOLICITACAO[s.status]}</span>
                  </div>
                </div>
                <p className="mt-2 text-sm italic" data-testid="sol-trecho">“{s.trecho_lead}”</p>
                <div className="mt-1 text-xs text-muted-foreground">
                  Prazo: {formatarDataHora(s.prazo_em)}
                  {s.decidido_em && ` · decidida em ${formatarDataHora(s.decidido_em)}`}
                  {s.motivo_decisao && ` · ${s.motivo_decisao}`}
                </div>
                {s.notificacao_status === "falhou" && (
                  <p className="mt-1 text-xs font-medium text-destructive" data-testid="sol-notificacao-falhou">
                    O aviso aos admins falhou: {s.notificacao_erro}
                  </p>
                )}
                {isAdmin && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {DECISOES.filter((d) => d.status !== s.status).map((d) => (
                      <Button
                        key={d.status} size="sm" variant="outline" disabled={decidir.isPending}
                        data-testid={`sol-${d.status}`}
                        onClick={() => (d.status === "negada" ? (setErro(null), setNegando(s)) : mover(s, d.status))}
                      >
                        {d.rotulo}
                      </Button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {paginas > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
          <span className="text-sm">{page} / {paginas}</span>
          <Button variant="outline" size="sm" disabled={page >= paginas} onClick={() => setPage(page + 1)}>Próxima</Button>
        </div>
      )}

      <MotivoDialog
        aberto={negando !== null} titulo="Negar solicitação"
        descricao="Registre o motivo da negativa (ex.: obrigação legal de guarda). Nada é apagado por esta ação."
        confirmar="Negar solicitação" pendente={decidir.isPending} erro={erro}
        onConfirmar={(m) => negando && mover(negando, "negada", m)} onFechar={() => setNegando(null)}
      />
    </div>
  );
}
