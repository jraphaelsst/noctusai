/**
 * Esteira de Produção — Módulo 4, the agency's production board.
 *
 * The board itself is `<EsteiraBoard/>` (seed `PipelineBoard` + the esteira's
 * move rules, card sheet and "nova tarefa"), shared with the Clientes card.
 * This page adds only the cliente filter, kept in the URL (`?cliente=<id>`) so
 * a filtered board is linkable and survives a reload (roadmap R9).
 *
 * `min-w-0` on the root: the board scrolls horizontally inside its own
 * container; the page never does (R0 — smoke finding 5).
 */
import { useSearchParams } from "react-router-dom";

import { EsteiraBoard } from "@/components/esteira/EsteiraBoard";
import { useClientes } from "@/hooks/useClientes";

export default function Esteira() {
  const [params, setParams] = useSearchParams();
  const clienteId = params.get("cliente") ?? "";
  const { clientes, loading } = useClientes();

  function filtrar(id: string) {
    const proximo = new URLSearchParams(params);
    if (id) proximo.set("cliente", id);
    else proximo.delete("cliente");
    setParams(proximo, { replace: true });
  }

  return (
    <div className="min-w-0 max-w-full space-y-4 p-4 sm:p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Esteira de Produção</h1>
          <p className="text-sm text-muted-foreground">
            Arraste o cartão uma etapa por vez. Para voltar, informe o motivo.
          </p>
        </div>
        <label className="block w-full sm:w-64">
          <span className="mb-1 block text-xs text-muted-foreground">Cliente</span>
          <select
            aria-label="Filtrar por cliente"
            value={clienteId}
            onChange={(e) => filtrar(e.target.value)}
            disabled={loading}
            className="h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground"
          >
            <option value="">Todos os clientes</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>
        </label>
      </header>

      <EsteiraBoard clienteId={clienteId || undefined} />
    </div>
  );
}
