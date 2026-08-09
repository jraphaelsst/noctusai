/**
 * Clientes — Módulo 1 (CRM).
 *
 * The first IgIg page wired to real data, so it is the reference for the
 * rest: all data access lives in `@/hooks/useClientes`, design tokens come
 * from the shared system (`bg-card`, `text-foreground`, `border-border`),
 * and the empty state is gated on `!loading` so it can never render over
 * data that is merely refetching.
 */
import { useState } from "react";
import { Badge, Button, Input, TableSkeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Plus, Search, Trash2, UserCheck } from "lucide-react";

import {
  useAtivarCliente,
  useClientes,
  useCriarCliente,
  useRemoverCliente,
  type StatusCliente,
} from "@/hooks/useClientes";

/** Badge tone per funnel status. Inadimplente is destructive because it
 *  gates the Módulo 4 approval portal — it needs to read as a problem. */
const STATUS_VARIANT: Record<StatusCliente, BadgeVariant> = {
  prospect: "muted",
  ativo: "default",
  inativo: "outline",
  // Inadimplente gates the Módulo 4 approval portal — it must read as a problem.
  inadimplente: "destructive",
};

const STATUS_LABEL: Record<StatusCliente, string> = {
  prospect: "Prospect",
  ativo: "Ativo",
  inativo: "Inativo",
  inadimplente: "Inadimplente",
};

export default function Clientes() {
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState<StatusCliente | "">("");
  const [novoNome, setNovoNome] = useState("");
  const [novoNicho, setNovoNicho] = useState("");

  const { clientes, total, loading, error } = useClientes({
    busca: busca || undefined,
    status: status || undefined,
  });
  const criar = useCriarCliente();
  const ativar = useAtivarCliente();
  const remover = useRemoverCliente();

  function handleCriar(event: React.FormEvent) {
    event.preventDefault();
    const nome = novoNome.trim();
    if (!nome) return;
    criar.mutate(
      { nome, nicho: novoNicho.trim() || undefined },
      {
        onSuccess: () => {
          setNovoNome("");
          setNovoNicho("");
        },
      },
    );
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Clientes</h1>
          <p className="text-sm text-muted-foreground">
            {loading ? "Carregando…" : `${total} ${total === 1 ? "cliente" : "clientes"}`}
          </p>
        </div>
      </header>

      {/* ── Novo cliente ─────────────────────────────────────────── */}
      <form
        onSubmit={handleCriar}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-4"
      >
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="nome" className="mb-1 block text-xs text-muted-foreground">
            Nome
          </label>
          <Input
            id="nome"
            value={novoNome}
            onChange={(e) => setNovoNome(e.target.value)}
            placeholder="Padaria Sol"
          />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label htmlFor="nicho" className="mb-1 block text-xs text-muted-foreground">
            Nicho
          </label>
          <Input
            id="nicho"
            value={novoNicho}
            onChange={(e) => setNovoNicho(e.target.value)}
            placeholder="Alimentação"
          />
        </div>
        <Button type="submit" disabled={!novoNome.trim() || criar.isPending}>
          <Plus className="mr-2 h-4 w-4" />
          {criar.isPending ? "Salvando…" : "Adicionar"}
        </Button>
      </form>

      {criar.isError && (
        <p className="text-sm text-destructive">
          Não foi possível criar o cliente. Verifique os dados e tente novamente.
        </p>
      )}

      {/* ── Filtros ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Buscar por nome"
            className="pl-9"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome…"
          />
        </div>
        <select
          aria-label="Filtrar por status"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusCliente | "")}
          className="h-10 rounded-md border border-border bg-card px-3 text-sm text-foreground"
        >
          <option value="">Todos os status</option>
          {(Object.keys(STATUS_LABEL) as StatusCliente[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>

      {/* ── Lista ────────────────────────────────────────────────── */}
      {error ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-destructive">
          Não foi possível carregar os clientes.
        </p>
      ) : loading ? (
        <TableSkeleton rows={5} />
      ) : clientes.length === 0 ? (
        /* Reached only when NOT loading — an empty state shown during a
           background refetch would be lying about the data. */
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          {busca || status
            ? "Nenhum cliente corresponde aos filtros."
            : "Nenhum cliente ainda. Adicione o primeiro acima."}
        </p>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
          {clientes.map((cliente) => (
            <li key={cliente.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-foreground">{cliente.nome}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {cliente.nicho || "Sem nicho definido"}
                </p>
              </div>

              <Badge variant={STATUS_VARIANT[cliente.status]}>
                {STATUS_LABEL[cliente.status]}
              </Badge>

              {cliente.status === "prospect" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => ativar.mutate(cliente.id)}
                  disabled={ativar.isPending}
                  aria-label={`Ativar ${cliente.nome}`}
                >
                  <UserCheck className="mr-2 h-4 w-4" />
                  Ativar
                </Button>
              )}

              <Button
                variant="ghost"
                size="sm"
                onClick={() => remover.mutate(cliente.id)}
                disabled={remover.isPending}
                aria-label={`Remover ${cliente.nome}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
