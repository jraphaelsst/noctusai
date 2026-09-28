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
 * Título/responsável/prazo/pauta are editable (achado 3 — before this, the
 * only way to fix any of them was delete + recreate, which loses every
 * apontamento). Delete is a two-step confirm inside the footer, and warns
 * about hours on the record before it asks the server to actually delete
 * (achado 4 — the server itself also refuses without confirmation).
 *
 * The "Repertório da marca" panel (achado 1 — the component existed but was
 * mounted nowhere) sits as a desktop side panel and a mobile collapsible
 * section, defaulting to the pauta's OWN marca when it has one.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { EntityDetailDialog } from "@noctusai/lib/components";
import { Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { ChevronDown, Copy, Link2, Pause, Pencil, Play, Trash2 } from "lucide-react";

import { RepertorioSidebar } from "@/components/RepertorioSidebar";
import { useClientes } from "@/hooks/useClientes";
import { useProfissionais } from "@/hooks/useCustos";
import {
  urlAprovacao,
  useApontamentos,
  useAtualizarTarefa,
  useEmitirLinkAprovacao,
  useEncerrarTimer,
  useExcluirTarefa,
  useIniciarTimer,
  type TarefaCard,
} from "@/hooks/useEsteira";
import { usePautas } from "@/hooks/usePautas";
import { describeError } from "@/lib/errors";
import { SHEET_MOBILE } from "@/lib/mobileSheet";
import { formatarMinutos, formatarPrazo, prazoVencido, rotuloPauta } from "./formatos";

type Modo = "ver" | "editar" | "excluir";

const CAMPO =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground";

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
  const { profissionais } = useProfissionais(true);
  const { pautas } = usePautas();
  const { clientes } = useClientes();
  const iniciar = useIniciarTimer();
  const encerrar = useEncerrarTimer();
  const emitirLink = useEmitirLinkAprovacao();
  const atualizar = useAtualizarTarefa();
  const excluir = useExcluirTarefa();

  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [modo, setModo] = useState<Modo>("ver");
  const [repertorioAberto, setRepertorioAberto] = useState(false);
  const [campos, setCampos] = useState({ titulo: "", responsavelId: "", prazo: "", pautaId: "" });

  // A different card (or the sheet closing) must never inherit the previous
  // card's link, a half-armed edit or delete.
  useEffect(() => {
    setLinkUrl(null);
    setModo("ver");
    setRepertorioAberto(false);
  }, [tarefaId]);

  if (!tarefa) {
    return <EntityDetailDialog open={false} onClose={onClose} title="" className={SHEET_MOBILE} />;
  }

  const nomeProfissional = (id: string | null) =>
    (id && profissionais.find((p) => p.id === id)?.nome) || "Sem profissional vinculado";
  const nomeCliente = (id: string) => clientes.find((c) => c.id === id)?.nome;

  function alternarTimer() {
    if (!tarefa) return;
    const mutacao = emAndamento ? encerrar : iniciar;
    mutacao.mutate(tarefa.id, {
      onError: (e) => toast.error(describeError(e, "Não foi possível atualizar o cronômetro.")),
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
      onError: (e) => toast.error(describeError(e, "Não foi possível gerar o link.")),
    });
  }

  function iniciarEdicao() {
    if (!tarefa) return;
    setCampos({
      titulo: tarefa.titulo,
      responsavelId: tarefa.responsavel_id ?? "",
      prazo: tarefa.prazo ?? "",
      pautaId: tarefa.pauta_id,
    });
    setModo("editar");
  }

  function salvarEdicao() {
    if (!tarefa) return;
    const titulo = campos.titulo.trim();
    if (!titulo) return;
    atualizar.mutate(
      {
        id: tarefa.id,
        titulo,
        responsavel_id: campos.responsavelId || null,
        prazo: campos.prazo || null,
        pauta_id: campos.pautaId,
      },
      {
        onSuccess: () => {
          toast.success("Tarefa atualizada.");
          setModo("ver");
        },
        onError: (e) => toast.error(describeError(e, "Não foi possível salvar a tarefa.")),
      },
    );
  }

  function confirmarExclusao() {
    if (!tarefa) return;
    // The hours are already loaded (`useApontamentos`) — the confirm step
    // below shows them, so reaching this handler IS the user's informed
    // confirmation; the server re-validates the figure regardless.
    excluir.mutate(
      { id: tarefa.id, confirmarPerdaHoras: minutosTotais > 0 },
      {
        onSuccess: () => {
          toast.success("Tarefa excluída");
          onClose();
        },
        onError: (e) => toast.error(describeError(e, "Não foi possível excluir a tarefa.")),
      },
    );
  }

  const vencido = prazoVencido(tarefa.prazo);
  const pautaAtual = pautas.find((p) => p.id === tarefa.pauta_id);

  const camposVisualizacao = [
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
  ];

  const camposEdicao = [
    {
      label: "Título",
      value: (
        <Input
          aria-label="Título da tarefa"
          className="h-9 max-w-xs"
          value={campos.titulo}
          onChange={(e) => setCampos((c) => ({ ...c, titulo: e.target.value }))}
        />
      ),
    },
    {
      label: "Pauta",
      value: (
        <select
          aria-label="Pauta da tarefa"
          className={`${CAMPO} h-9 max-w-xs`}
          value={campos.pautaId}
          onChange={(e) => setCampos((c) => ({ ...c, pautaId: e.target.value }))}
        >
          {pautas.map((p) => (
            <option key={p.id} value={p.id}>{rotuloPauta(p, nomeCliente(p.cliente_id))}</option>
          ))}
        </select>
      ),
    },
    {
      label: "Responsável",
      value: (
        <select
          aria-label="Responsável pela tarefa"
          className={`${CAMPO} h-9 max-w-xs`}
          value={campos.responsavelId}
          onChange={(e) => setCampos((c) => ({ ...c, responsavelId: e.target.value }))}
        >
          <option value="">Sem responsável</option>
          {profissionais.map((p) => (
            <option key={p.id} value={p.id}>{p.nome}</option>
          ))}
        </select>
      ),
    },
    {
      label: "Prazo",
      value: (
        <Input
          type="date"
          aria-label="Prazo da tarefa"
          className="h-9 max-w-xs"
          value={campos.prazo}
          onChange={(e) => setCampos((c) => ({ ...c, prazo: e.target.value }))}
        />
      ),
    },
  ];

  const acoes =
    modo === "excluir"
      ? [
          {
            label: excluir.isPending ? "Excluindo…" : "Confirmar exclusão",
            variant: "destructive" as const,
            align: "start" as const,
            disabled: excluir.isPending,
            onClick: confirmarExclusao,
            testId: "tarefa-confirmar-exclusao",
          },
          { label: "Cancelar", variant: "ghost" as const, onClick: () => setModo("ver") },
        ]
      : modo === "editar"
        ? [
            {
              label: atualizar.isPending ? "Salvando…" : "Salvar",
              variant: "primary" as const,
              align: "start" as const,
              disabled: atualizar.isPending || !campos.titulo.trim(),
              onClick: salvarEdicao,
              testId: "tarefa-salvar-edicao",
            },
            { label: "Cancelar", variant: "ghost" as const, onClick: () => setModo("ver") },
          ]
        : [
            {
              label: "Editar",
              variant: "ghost" as const,
              align: "start" as const,
              icon: <Pencil className="h-4 w-4" />,
              onClick: iniciarEdicao,
              testId: "tarefa-editar",
            },
            {
              label: "Excluir tarefa",
              variant: "ghost" as const,
              align: "start" as const,
              icon: <Trash2 className="h-4 w-4" />,
              onClick: () => setModo("excluir"),
              testId: "tarefa-excluir",
            },
            { label: "Fechar", variant: "outline" as const, onClick: onClose },
          ];

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
        modo === "excluir" && minutosTotais > 0 ? (
          <span className="text-destructive">
            Esta tarefa tem {formatarMinutos(minutosTotais)} de horas apontadas em{" "}
            {apontamentos.length} {apontamentos.length === 1 ? "apontamento" : "apontamentos"}.
            Excluir perde esses registros.
          </span>
        ) : tarefa.observacao_cliente ? (
          <span>Cliente pediu: “{tarefa.observacao_cliente}”</span>
        ) : undefined
      }
      sections={[{ fields: modo === "editar" ? camposEdicao : camposVisualizacao }]}
      actions={acoes}
    >
      <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1 space-y-5">
          {/* Repertório — collapsible on the phone, ambient chrome only. */}
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-md border border-border p-2 text-left text-sm text-foreground sm:hidden"
            onClick={() => setRepertorioAberto((v) => !v)}
            aria-expanded={repertorioAberto}
          >
            Repertório da marca
            <ChevronDown
              className={`h-4 w-4 transition-transform ${repertorioAberto ? "rotate-180" : ""}`}
            />
          </button>
          {repertorioAberto && (
            <div className="sm:hidden">
              <RepertorioSidebar
                clienteId={tarefa.cliente?.id}
                marcaIdPreferida={pautaAtual?.marca_id ?? tarefa.pauta?.marca_id}
                className="w-full"
              />
            </div>
          )}

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

        {/* Repertório — a fixed side panel on desktop. */}
        <div className="hidden sm:block">
          <RepertorioSidebar
            clienteId={tarefa.cliente?.id}
            marcaIdPreferida={pautaAtual?.marca_id ?? tarefa.pauta?.marca_id}
          />
        </div>
      </div>
    </EntityDetailDialog>
  );
}
