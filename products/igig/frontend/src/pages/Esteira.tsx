/**
 * Esteira de Produção — Módulo 4, the agency's internal kanban.
 *
 * Column order comes from the backend (`quadro.etapas`), not a local constant:
 * the 8-step sequence is a business rule, and a frontend that invented its own
 * ordering would drift from the DB CHECK constraint that enforces it.
 *
 * Movement is a select rather than drag-and-drop. The spec calls the flow
 * "sequencial rígido", and a select is unambiguous, keyboard-accessible, and
 * does not need a DnD dependency to be usable. Drag-and-drop can layer on top
 * later without changing this contract.
 */
import { useState } from "react";
import { useAuthStore } from "@noctusai/seed/infra";
import { Badge, Button, Input, TableSkeleton } from "@noctusai/lib/design-system";
import { Copy, Link2, Play, Plus, Square } from "lucide-react";

import {
  ETAPA_LABEL,
  useCriarTarefa,
  useEmitirLinkAprovacao,
  useEncerrarTimer,
  useIniciarTimer,
  useMoverTarefa,
  useQuadro,
  type Etapa,
  type Tarefa,
} from "@/hooks/useEsteira";
import { usePautas } from "@/hooks/usePautas";
import { useProfissionais } from "@/hooks/useCustos";

function CartaoTarefa({
  tarefa,
  etapas,
  onCopiarLink,
  usuarioId,
}: {
  tarefa: Tarefa;
  etapas: Etapa[];
  onCopiarLink: (token: string) => void;
  /** The signed-in user. Apontamentos are per-person, so a shared stand-in
   *  made every hour in the timesheet belong to the same fictional user and
   *  the custo real per profissional could never be attributed. */
  usuarioId: string;
}) {
  const mover = useMoverTarefa();
  const iniciar = useIniciarTimer();
  const encerrar = useEncerrarTimer();
  const emitirLink = useEmitirLinkAprovacao();

  return (
    <li className="rounded-md border border-border bg-background p-3">
      <p className="text-sm font-medium text-foreground">{tarefa.titulo}</p>

      {tarefa.refacoes > 0 && (
        <Badge variant="destructive" className="mt-2">
          {tarefa.refacoes} {tarefa.refacoes === 1 ? "refação" : "refações"}
        </Badge>
      )}

      {tarefa.observacao_cliente && (
        <p className="mt-2 rounded bg-muted p-2 text-xs text-muted-foreground">
          “{tarefa.observacao_cliente}”
        </p>
      )}

      <label className="mt-3 block">
        <span className="sr-only">Mover {tarefa.titulo} de etapa</span>
        <select
          value={tarefa.etapa}
          disabled={mover.isPending}
          onChange={(e) => mover.mutate({ id: tarefa.id, etapa: e.target.value as Etapa })}
          className="w-full rounded border border-border bg-card px-2 py-1 text-xs text-foreground"
        >
          {etapas.map((etapa) => (
            <option key={etapa} value={etapa}>
              {ETAPA_LABEL[etapa]}
            </option>
          ))}
        </select>
      </label>

      <div className="mt-2 flex flex-wrap gap-1">
        <Button
          variant="ghost"
          size="sm"
          disabled={iniciar.isPending}
          onClick={() => iniciar.mutate({ tarefaId: tarefa.id, usuarioId })}
          aria-label={`Iniciar cronômetro em ${tarefa.titulo}`}
        >
          <Play className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={encerrar.isPending}
          onClick={() => encerrar.mutate({ tarefaId: tarefa.id, usuarioId })}
          aria-label={`Pausar cronômetro em ${tarefa.titulo}`}
        >
          <Square className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={emitirLink.isPending}
          onClick={() =>
            emitirLink.mutate(tarefa.id, {
              onSuccess: (link) => onCopiarLink(link.token),
            })
          }
          aria-label={`Gerar link de aprovação para ${tarefa.titulo}`}
        >
          <Link2 className="h-3 w-3" />
        </Button>
      </div>
    </li>
  );
}

export default function Esteira() {
  const { quadro, loading, error } = useQuadro();
  const { user } = useAuthStore();
  const { pautas } = usePautas();
  const { profissionais } = useProfissionais();
  const criar = useCriarTarefa();

  const [linkCopiado, setLinkCopiado] = useState<string | null>(null);
  const [pautaId, setPautaId] = useState("");
  const [titulo, setTitulo] = useState("");
  const [responsavelId, setResponsavelId] = useState("");
  const [prazo, setPrazo] = useState("");

  const usuarioId = user?.id ?? "";

  function handleCriar(event: React.FormEvent) {
    event.preventDefault();
    const t = titulo.trim();
    if (!t || !pautaId) return;
    criar.mutate(
      {
        pauta_id: pautaId,
        titulo: t,
        responsavel_id: responsavelId || null,
        prazo: prazo || null,
      },
      { onSuccess: () => { setTitulo(""); setPrazo(""); setResponsavelId(""); } },
    );
  }

  function handleCopiarLink(token: string) {
    const url = `${window.location.origin}/aprovar/${token}`;
    setLinkCopiado(url);
    // Clipboard access can be denied (insecure context, permissions). The URL
    // is shown on screen regardless, so a refusal degrades to copy-by-hand
    // rather than losing the link.
    void navigator.clipboard?.writeText(url).catch(() => undefined);
  }

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Esteira de Produção</h1>
        <p className="text-sm text-muted-foreground">
          Fluxo sequencial das peças, do roteiro ao agendamento.
        </p>
      </header>

      {/* ── Nova tarefa ────────────────────────────────────────────
          A tarefa always belongs to a pauta, so the pauta selector is
          required rather than optional — creating one without it would 404
          at the backend, which checks the parent explicitly. */}
      {pautas.length === 0 ? (
        <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
          Nenhuma pauta cadastrada ainda. Crie uma pauta no{" "}
          <a href="/calendario" className="underline">Calendário Editorial</a>{" "}
          para poder abrir tarefas na esteira.
        </p>
      ) : (
        <form
          onSubmit={handleCriar}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-4"
        >
          <div className="min-w-[200px] flex-1">
            <label htmlFor="tarefa-titulo" className="mb-1 block text-xs text-muted-foreground">
              Nova tarefa
            </label>
            <Input
              id="tarefa-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Carrossel — lançamento de outubro"
            />
          </div>
          <div className="min-w-[180px]">
            <label htmlFor="tarefa-pauta" className="mb-1 block text-xs text-muted-foreground">
              Pauta
            </label>
            <select
              id="tarefa-pauta"
              value={pautaId}
              onChange={(e) => setPautaId(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
            >
              <option value="">Selecione…</option>
              {pautas.map((p) => (
                <option key={p.id} value={p.id}>{p.titulo}</option>
              ))}
            </select>
          </div>
          <div className="min-w-[170px]">
            <label htmlFor="tarefa-responsavel" className="mb-1 block text-xs text-muted-foreground">
              Responsável
            </label>
            <select
              id="tarefa-responsavel"
              value={responsavelId}
              onChange={(e) => setResponsavelId(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
            >
              <option value="">Sem responsável</option>
              {profissionais.map((p) => (
                <option key={p.id} value={p.id}>{p.nome}</option>
              ))}
            </select>
          </div>
          <div className="min-w-[150px]">
            <label htmlFor="tarefa-prazo" className="mb-1 block text-xs text-muted-foreground">
              Prazo
            </label>
            <Input
              id="tarefa-prazo"
              type="date"
              value={prazo}
              onChange={(e) => setPrazo(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={!titulo.trim() || !pautaId || criar.isPending}>
            <Plus className="mr-2 h-4 w-4" />
            {criar.isPending ? "Criando…" : "Criar tarefa"}
          </Button>
        </form>
      )}

      {criar.isError && (
        <p className="text-sm text-destructive">
          Não foi possível criar a tarefa. Verifique a pauta selecionada e tente novamente.
        </p>
      )}

      {linkCopiado && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card p-3 text-sm">
          <Copy className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-muted-foreground">Link de aprovação:</span>
          <code className="truncate text-foreground">{linkCopiado}</code>
        </div>
      )}

      {error ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-destructive">
          Não foi possível carregar a esteira.
        </p>
      ) : loading ? (
        <TableSkeleton rows={4} />
      ) : !quadro ? null : (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {quadro.etapas.map((etapa) => {
            const tarefas = quadro.colunas[etapa] ?? [];
            return (
              <section
                key={etapa}
                className="w-64 shrink-0 rounded-lg border border-border bg-card p-3"
              >
                <h2 className="mb-3 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {ETAPA_LABEL[etapa]}
                  <span className="text-foreground">{tarefas.length}</span>
                </h2>
                {tarefas.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Vazio</p>
                ) : (
                  <ul className="space-y-2">
                    {tarefas.map((tarefa) => (
                      <CartaoTarefa
                        key={tarefa.id}
                        tarefa={tarefa}
                        etapas={quadro.etapas}
                        onCopiarLink={handleCopiarLink}
                        usuarioId={usuarioId}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
