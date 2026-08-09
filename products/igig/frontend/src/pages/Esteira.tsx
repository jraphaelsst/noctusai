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
import { Badge, Button, TableSkeleton } from "@noctusai/lib/design-system";
import { Copy, Link2, Play, Square } from "lucide-react";

import {
  ETAPA_LABEL,
  useEmitirLinkAprovacao,
  useEncerrarTimer,
  useIniciarTimer,
  useMoverTarefa,
  useQuadro,
  type Etapa,
  type Tarefa,
} from "@/hooks/useEsteira";

/** Stand-in until the timesheet is bound to the signed-in user's id. */
const USUARIO_ATUAL = "usuario-atual";

function CartaoTarefa({
  tarefa,
  etapas,
  onCopiarLink,
}: {
  tarefa: Tarefa;
  etapas: Etapa[];
  onCopiarLink: (token: string) => void;
}) {
  const mover = useMoverTarefa();
  const iniciar = useIniciarTimer();
  const encerrar = useEncerrarTimer();
  const emitirLink = useEmitirLinkAprovacao();

  return (
    <li className="rounded-md border border-border bg-background p-3">
      <p className="text-sm font-medium text-foreground">{tarefa.titulo}</p>

      {tarefa.refacoes > 0 && (
        <Badge variant={"destructive" as never} className="mt-2">
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
          onClick={() => iniciar.mutate({ tarefaId: tarefa.id, usuarioId: USUARIO_ATUAL })}
          aria-label={`Iniciar cronômetro em ${tarefa.titulo}`}
        >
          <Play className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={encerrar.isPending}
          onClick={() => encerrar.mutate({ tarefaId: tarefa.id, usuarioId: USUARIO_ATUAL })}
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
  const [linkCopiado, setLinkCopiado] = useState<string | null>(null);

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
