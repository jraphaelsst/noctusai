/**
 * The detail sheet of one esteira card — the seed `EntityDetailDialog` organ
 * (full-screen sheet <640px, R0), with the tarefa's three working surfaces
 * under the field grid:
 *
 *  - TIMER — play/pause for the signed-in user. No `usuario_id` is sent: the
 *    server times the authenticated caller (smoke finding 3).
 *  - APONTAMENTOS — the timesheet segments, attributed through the
 *    `profissional` the server recorded (smoke finding 8), never a raw user id.
 *  - LINK DE APROVAÇÃO — minting it moves the card into approval server-side;
 *    the URL is copied AND shown, so a clipboard refusal never loses it.
 *
 * Delete is a two-step confirm inside the footer: a destructive action one
 * accidental tap away is the wrong default on a phone.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { EntityDetailDialog } from "@noctusai/lib/components";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { Copy, Link2, Pause, Play, Trash2 } from "lucide-react";

import { useProfissionais } from "@/hooks/useCustos";
import {
  urlAprovacao,
  useApontamentos,
  useEmitirLinkAprovacao,
  useEncerrarTimer,
  useExcluirTarefa,
  useIniciarTimer,
  type TarefaCard,
} from "@/hooks/useEsteira";
import { SHEET_MOBILE } from "@/lib/mobileSheet";
import { formatarMinutos, formatarPrazo, prazoVencido } from "./formatos";

function mensagemDe(erro: unknown, padrao: string): string {
  return erro instanceof Error && erro.message ? erro.message : padrao;
}

export function TarefaDetalhe({
  tarefa,
  etapaLabel,
  usuarioId,
  onClose,
}: {
  tarefa: TarefaCard | null;
  etapaLabel: string | null;
  usuarioId: string | null;
  onClose: () => void;
}) {
  const aberta = tarefa !== null;
  const tarefaId = tarefa?.id ?? null;

  const { apontamentos, emAndamento, minutosTotais, loading, error } = useApontamentos(
    tarefaId,
    usuarioId,
  );
  const { profissionais } = useProfissionais();
  const iniciar = useIniciarTimer();
  const encerrar = useEncerrarTimer();
  const emitirLink = useEmitirLinkAprovacao();
  const excluir = useExcluirTarefa();

  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);

  // A different card (or the sheet closing) must never inherit the previous
  // card's link or a half-armed delete.
  useEffect(() => {
    setLinkUrl(null);
    setConfirmandoExclusao(false);
  }, [tarefaId]);

  if (!tarefa) {
    return <EntityDetailDialog open={false} onClose={onClose} title="" className={SHEET_MOBILE} />;
  }

  const nomeProfissional = (id: string | null) =>
    (id && profissionais.find((p) => p.id === id)?.nome) || "Sem profissional vinculado";

  function alternarTimer() {
    if (!tarefa) return;
    const mutacao = emAndamento ? encerrar : iniciar;
    mutacao.mutate(tarefa.id, {
      onError: (e) => toast.error(mensagemDe(e, "Não foi possível atualizar o cronômetro.")),
    });
  }

  function gerarLink() {
    if (!tarefa) return;
    emitirLink.mutate(tarefa.id, {
      onSuccess: (link) => {
        const url = urlAprovacao(link.token);
        setLinkUrl(url);
        // Clipboard can be refused (insecure context, permissions); the URL
        // stays on screen, so a refusal degrades to copy-by-hand.
        navigator.clipboard
          ?.writeText(url)
          .then(() => toast.success("Link copiado — a tarefa foi para aprovação do cliente."))
          .catch(() => toast.message("Copie o link abaixo e envie ao cliente."));
      },
      onError: (e) => toast.error(mensagemDe(e, "Não foi possível gerar o link.")),
    });
  }

  function confirmarExclusao() {
    if (!tarefa) return;
    excluir.mutate(tarefa.id, {
      onSuccess: () => {
        toast.success("Tarefa excluída");
        onClose();
      },
      onError: (e) => toast.error(mensagemDe(e, "Não foi possível excluir a tarefa.")),
    });
  }

  const vencido = prazoVencido(tarefa.prazo);

  return (
    <EntityDetailDialog
      open={aberta}
      onClose={onClose}
      title={tarefa.titulo}
      subtitle={tarefa.cliente?.nome}
      className={SHEET_MOBILE}
      testId="tarefa-detalhe"
      badges={[
        ...(etapaLabel ? [{ label: etapaLabel, variant: "outline" as const }] : []),
        ...(tarefa.refacoes > 0
          ? [{
              label: `${tarefa.refacoes} ${tarefa.refacoes === 1 ? "refação" : "refações"}`,
              variant: "destructive" as const,
            }]
          : []),
      ]}
      note={
        tarefa.observacao_cliente ? (
          <span>Cliente pediu: “{tarefa.observacao_cliente}”</span>
        ) : undefined
      }
      sections={[
        {
          fields: [
            { label: "Cliente", value: tarefa.cliente?.nome },
            { label: "Pauta", value: tarefa.pauta?.titulo },
            { label: "Formato", value: tarefa.pauta?.formato },
            { label: "Responsável", value: tarefa.responsavel?.nome },
            {
              label: "Prazo",
              value: tarefa.prazo ? (
                <span className={vencido ? "font-medium text-destructive" : undefined}>
                  {formatarPrazo(tarefa.prazo)}
                  {vencido && " · vencido"}
                </span>
              ) : null,
            },
            {
              label: "Publicação",
              value: tarefa.pauta?.data_publicacao
                ? new Date(tarefa.pauta.data_publicacao).toLocaleDateString("pt-BR")
                : null,
            },
          ],
        },
      ]}
      actions={
        confirmandoExclusao
          ? [
              {
                label: excluir.isPending ? "Excluindo…" : "Confirmar exclusão",
                variant: "destructive",
                align: "start",
                disabled: excluir.isPending,
                onClick: confirmarExclusao,
                testId: "tarefa-confirmar-exclusao",
              },
              { label: "Cancelar", variant: "ghost", onClick: () => setConfirmandoExclusao(false) },
            ]
          : [
              {
                label: "Excluir tarefa",
                variant: "ghost",
                align: "start",
                icon: <Trash2 className="h-4 w-4" />,
                onClick: () => setConfirmandoExclusao(true),
                testId: "tarefa-excluir",
              },
              { label: "Fechar", variant: "outline", onClick: onClose },
            ]
      }
    >
      <div className="mt-5 space-y-5">
        {/* ── Timer ─────────────────────────────────────────── */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tempo
          </h3>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant={emAndamento ? "destructive" : "primary"}
              className="min-h-11"
              disabled={iniciar.isPending || encerrar.isPending || loading}
              onClick={alternarTimer}
              aria-pressed={Boolean(emAndamento)}
            >
              {emAndamento ? (
                <><Pause className="mr-2 h-4 w-4" />Pausar</>
              ) : (
                <><Play className="mr-2 h-4 w-4" />Iniciar</>
              )}
            </Button>
            <span className="text-sm text-muted-foreground">
              {emAndamento
                ? `Rodando desde ${new Date(emAndamento.iniciado_em).toLocaleTimeString("pt-BR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}`
                : `Total: ${formatarMinutos(minutosTotais)}`}
            </span>
          </div>
        </section>

        {/* ── Apontamentos ──────────────────────────────────── */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Apontamentos
          </h3>
          {error ? (
            <p className="text-sm text-destructive">Não foi possível carregar os apontamentos.</p>
          ) : loading ? (
            <Skeleton className="h-10 w-full" />
          ) : apontamentos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum tempo registrado ainda.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border text-sm">
              {apontamentos.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-2">
                  <span className="min-w-0 truncate text-foreground">
                    {nomeProfissional(a.profissional_id)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(a.iniciado_em).toLocaleString("pt-BR", {
                      day: "2-digit",
                      month: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {" · "}
                    {a.encerrado_em ? formatarMinutos(a.minutos) : "em andamento"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ── Link de aprovação ─────────────────────────────── */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Aprovação do cliente
          </h3>
          <Button
            variant="outline"
            className="min-h-11"
            disabled={emitirLink.isPending}
            onClick={gerarLink}
          >
            <Link2 className="mr-2 h-4 w-4" />
            {emitirLink.isPending ? "Gerando…" : "Gerar e copiar link de aprovação"}
          </Button>
          {linkUrl && (
            <div className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-muted p-2 text-xs">
              <Copy className="h-3 w-3 shrink-0 text-muted-foreground" />
              <code className="min-w-0 break-all text-foreground" data-testid="tarefa-link-url">
                {linkUrl}
              </code>
            </div>
          )}
        </section>
      </div>
    </EntityDetailDialog>
  );
}
