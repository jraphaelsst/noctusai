/**
 * Calendário Editorial — Módulo 3.
 *
 * The calendar itself is `<CalendarioMes/>` (month grid ≥640px, agenda list on
 * phones, copy editor, peças), shared with the Clientes card's Calendário tab.
 * This page is the all-clientes mount, with a cliente filter kept in the URL
 * (`?cliente=<id>`) — the Esteira page already had one (`/esteira?cliente=`);
 * the Calendário page didn't (achado 26), the one place a linkable
 * one-cliente view previously required the Clientes card instead.
 */
import { useSearchParams } from "react-router-dom";

import { CalendarioMes } from "@/components/calendario/CalendarioMes";
import { useClientes } from "@/hooks/useClientes";

export default function Calendario() {
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
          <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Calendário Editorial</h1>
          <p className="text-sm text-muted-foreground">
            <span className="hidden sm:inline">Arraste uma pauta para outro dia para reagendar. </span>
            Toque numa pauta para editar a legenda, as peças e a data.
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
      <CalendarioMes clienteId={clienteId || undefined} />
    </div>
  );
}
