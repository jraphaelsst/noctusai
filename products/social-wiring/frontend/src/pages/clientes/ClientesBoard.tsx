/**
 * Clientes — the person board at `/clientes` (lead-card-hub Phase 1,
 * PROJECT.md §5, §6 Slice C). "Cards are LEADS" on `/funil` (see
 * `FunilVendas.tsx`); here, cards are PEOPLE — the Phase 1 checkpoint's "the
 * board shows one card per human". This page is ADDITIVE alongside the
 * existing leads-based pages (Leads / Funil / Processos), not a replacement
 * — Phase 1 does not retire the `leads` table workflows, only lays the
 * `clientes` foundation Phases 2-5 attach to.
 *
 * Default **active only** (D4, §5). Inactive people are reachable via the
 * "Inativos" tab and restorable in-place (PATCH `ativo: true`) — never a
 * separate "trash" flow.
 *
 * States: loading / error / empty-because-no-filters-match /
 * empty-because-genuinely-no-clientes / success.
 *
 * Route: /clientes. Nav entry lives in BOTH NAV_GROUPS and NAV_FALLBACK in
 * App.tsx (the Imóveis precedent — missing either one is a known trap), and
 * needs its own `status_pagina` row (owned by the backend/migration slice)
 * or the seed's `filterNavByPageStatus` gate hides the link with no error
 * anywhere — flagged in this slice's delivery note.
 */
import { useState } from "react";
import { AlertCircle, Search, Users, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { ClienteCard } from "@/components/clientes/ClienteCard";
import { ClienteDetailModal } from "@/components/ClienteDetailModal";
import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import {
  useClienteMutations,
  useClientesBoard,
  type Cliente,
  type ClientesFiltros,
} from "@/hooks/useClientes";

const PAGE_SIZE = 24;
const ALL = "__all__";

export default function ClientesBoard() {
  const [statusTab, setStatusTab] = useState<"ativos" | "inativos">("ativos");
  const [page, setPage] = useState(1);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState<string | undefined>(undefined);
  const [corretorId, setCorretorId] = useState<string | undefined>(undefined);
  // lead-card-hub Phase 2 (PROJECT.md §4): the board had no click target at
  // all. Opening a cliente mounts the ONE card detail dialog — the same
  // component the funil board will mount once slice `054` lands.
  const [openClienteId, setOpenClienteId] = useState<string | null>(null);

  const filtros: ClientesFiltros = {
    page,
    page_size: PAGE_SIZE,
    // Omitted for "ativos" — the server default already means active-only
    // (D4); only the inactive tab needs an explicit `ativo=false`.
    ativo: statusTab === "inativos" ? false : undefined,
    q: search,
    corretor_id: corretorId,
  };

  const board = useClientesBoard(filtros);
  const corretores = useLeadCorretores();
  const { update } = useClienteMutations();

  // Gate on isPending || isFetching, never isLoading — TanStack v5's
  // `isLoading` is false during a background refetch, so an isEmpty branch
  // keyed on it would flash "nenhum cliente" over data that still exists.
  const loading = board.isPending || board.isFetching;
  const data = board.data;
  const hasFilters = Boolean(search || corretorId);
  const isEmpty = !loading && !board.isError && (data?.items.length ?? 0) === 0;

  function patchTab(tab: "ativos" | "inativos") {
    setStatusTab(tab);
    setPage(1);
  }

  function submitSearch() {
    setSearch(searchDraft || undefined);
    setPage(1);
  }

  function clearFilters() {
    setSearchDraft("");
    setSearch(undefined);
    setCorretorId(undefined);
    setPage(1);
  }

  function restore(cliente: Cliente) {
    update.mutate({ id: cliente.id, body: { ativo: true } });
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Clientes</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total.toLocaleString("pt-BR")} pessoas` : "Carregando…"}
          </p>
        </div>
        <Tabs value={statusTab} onValueChange={(v) => patchTab(v as "ativos" | "inativos")}>
          <TabsList>
            <TabsTrigger value="ativos" data-testid="clientes-tab-ativos">
              Ativos
            </TabsTrigger>
            <TabsTrigger value="inativos" data-testid="clientes-tab-inativos">
              Inativos
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <Card>
        <CardContent className="flex flex-wrap gap-3 p-4">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Buscar por nome, telefone ou e-mail…"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitSearch();
              }}
            />
          </div>

          <Select
            value={corretorId ?? ALL}
            onValueChange={(v) => {
              setCorretorId(v === ALL ? undefined : v);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Corretor" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Corretor: todos</SelectItem>
              {(corretores.data ?? []).map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.nome}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <X className="mr-1 h-4 w-4" />
              Limpar
            </Button>
          )}
        </CardContent>
      </Card>

      {board.isError ? (
        <ErrorState onRetry={() => board.refetch()} />
      ) : loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full rounded-lg" />
          ))}
        </div>
      ) : isEmpty ? (
        hasFilters ? (
          <EmptyFiltered onClear={clearFilters} />
        ) : (
          <EmptyNoClientes tab={statusTab} />
        )
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {data!.items.map((cliente) => (
              <ClienteCard
                key={cliente.id}
                cliente={cliente}
                onRestore={restore}
                restoring={update.isPending && update.variables?.id === cliente.id}
                onOpen={(c) => setOpenClienteId(c.id)}
              />
            ))}
          </div>

          {data!.pages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={data!.page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {data!.page} de {data!.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={data!.page >= data!.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}

      <ClienteDetailModal
        clienteId={openClienteId}
        open={!!openClienteId}
        onClose={() => setOpenClienteId(null)}
      />
    </div>
  );
}

// ─── States ─────────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os clientes.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyFiltered({ onClear }: { onClear: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Search className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Nenhum cliente corresponde aos filtros.</p>
          <p className="text-sm text-muted-foreground">
            Sua base não está vazia — só esta combinação de filtros.
          </p>
        </div>
        <Button variant="outline" onClick={onClear}>
          Limpar filtros
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyNoClientes({ tab }: { tab: "ativos" | "inativos" }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Users className="h-10 w-10 text-muted-foreground" />
        <p className="font-medium">
          {tab === "inativos"
            ? "Nenhum cliente inativo."
            : "Nenhum cliente ativo ainda."}
        </p>
      </CardContent>
    </Card>
  );
}
