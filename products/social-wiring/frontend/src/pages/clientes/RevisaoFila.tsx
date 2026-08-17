/**
 * Fila de Revisão — the review queue at `/clientes/revisao` (lead-card-hub
 * Phase 1, PROJECT.md §5, §6 Slice C — the slice's PRIMARY deliverable).
 *
 * ~311 groups (C4-C6, PROJECT.md §3) where identity resolution could not
 * auto-decide. Each group shows every candidate person, the reason code,
 * and two actions: merge or "manter separados". PROJECT.md §8's checkpoint
 * requires the queue be WALKABLE — this page paginates, keeps the
 * operator's position after an action (a resolved group is filtered out of
 * the LOCAL render immediately, not just after the next refetch, so it can
 * never flash back), and auto-advances past a page that empties out from
 * under the operator instead of showing a dead page.
 *
 * A merge is reversible (D3) — the success toast surfaces "Desfazer" wired
 * to `POST /api/clientes/merges/{id}/desfazer`, because an operator who
 * believes a merge is permanent will not use the queue.
 *
 * States: loading / error / **empty queue = SUCCESS** ("nothing left to
 * review" is the goal — this must never look like a failed load) / success
 * (groups to review). No "genuinely empty because no filters" branch — this
 * page has no filters, only pagination.
 *
 * Route: /clientes/revisao. Nav entry lives in BOTH NAV_GROUPS and
 * NAV_FALLBACK in App.tsx, and needs its own `status_pagina` row (backend
 * slice) — flagged in this slice's delivery note.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { RevisaoGrupoCard } from "@/components/clientes/RevisaoGrupoCard";
import {
  DEFAULT_REVISAO_PAGE_SIZE,
  useRevisaoFila,
  useRevisaoMutations,
  type RevisaoGrupo,
} from "@/hooks/useClientesRevisao";

export default function RevisaoFila() {
  const [page, setPage] = useState(1);
  // Groups the operator has already acted on THIS session — filtered out of
  // the render immediately so a stale/cached page can never re-present one,
  // ahead of the invalidated query's refetch actually landing.
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());

  const filtros = { page, page_size: DEFAULT_REVISAO_PAGE_SIZE };
  const queue = useRevisaoFila(filtros);
  const { merge, manterSeparados, desfazer } = useRevisaoMutations();

  // Gate on isPending || isFetching, never isLoading (same rule as every
  // other page in this product — TanStack v5's isLoading is false mid-refetch).
  const loading = queue.isPending || queue.isFetching;
  const data = queue.data;
  const visibleItems = (data?.items ?? []).filter((g) => !resolvedIds.has(g.chave_canonica));
  const isSuccessEmpty = !loading && !queue.isError && (data?.total ?? 0) === 0;

  // Walkability: a page that empties out purely because everything on it
  // got resolved this session (not because the queue is actually done)
  // auto-advances, so the operator is never staring at a blank page they
  // have to manually click past.
  useEffect(() => {
    if (
      !loading &&
      data &&
      data.total > 0 &&
      visibleItems.length === 0 &&
      data.items.length > 0 &&
      page < data.pages
    ) {
      setPage((p) => p + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, data, visibleItems.length, page]);

  function markResolved(grupoId: string) {
    setResolvedIds((prev) => new Set(prev).add(grupoId));
  }

  function handleMerge(grupo: RevisaoGrupo) {
    merge.mutate(
      { grupoId: grupo.chave_canonica },
      {
        onSuccess: (result) => {
          markResolved(grupo.chave_canonica);
          toast.success("Grupo mesclado.", {
            description: `As ${grupo.candidatos.length} pessoas foram unidas em um único cliente.`,
            duration: 10000,
            action: {
              label: "Desfazer",
              onClick: () => {
                desfazer.mutate(result.merge_id, {
                  onSuccess: () => toast.success("Mesclagem desfeita."),
                  onError: (err) =>
                    toast.error("Não foi possível desfazer a mesclagem.", {
                      description: err instanceof Error ? err.message : undefined,
                    }),
                });
              },
            },
          });
        },
        onError: (err) =>
          toast.error("Erro ao mesclar o grupo.", {
            description: err instanceof Error ? err.message : undefined,
          }),
      },
    );
  }

  function handleManterSeparados(grupo: RevisaoGrupo) {
    manterSeparados.mutate(grupo.chave_canonica, {
      onSuccess: () => {
        markResolved(grupo.chave_canonica);
        toast.success("Mantidos separados.", {
          description: "Este grupo não vai mais aparecer na fila de revisão.",
        });
      },
      onError: (err) =>
        toast.error("Erro ao salvar a decisão.", {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Fila de Revisão</h1>
        <p className="text-sm text-muted-foreground">
          {data
            ? `${data.total.toLocaleString("pt-BR")} grupo(s) aguardando revisão.`
            : "Carregando…"}
        </p>
      </div>

      {queue.isError ? (
        <ErrorState onRetry={() => queue.refetch()} />
      ) : loading && !data ? (
        <LoadingState />
      ) : isSuccessEmpty ? (
        <SuccessEmptyState />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            {visibleItems.map((grupo) => (
              <RevisaoGrupoCard
                key={grupo.chave_canonica}
                grupo={grupo}
                onMerge={handleMerge}
                onManterSeparados={handleManterSeparados}
                merging={merge.isPending && merge.variables?.grupoId === grupo.chave_canonica}
                rejecting={
                  manterSeparados.isPending && manterSeparados.variables === grupo.chave_canonica
                }
              />
            ))}
          </div>

          {data && data.pages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={data.page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {data.page} de {data.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={data.page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── States ─────────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="revisao-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-56 w-full rounded-lg" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar a fila de revisão.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

/**
 * A finished queue is the GOAL, not a failure — this deliberately does not
 * share ErrorState's/EmptyFiltered's visual language (no AlertCircle, no
 * "nada encontrado" phrasing). Green check + positive copy only.
 */
function SuccessEmptyState() {
  return (
    <Card className="border-emerald-500/30 bg-emerald-500/5" data-testid="revisao-empty-success">
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <CheckCircle2 className="h-10 w-10 text-emerald-600" />
        <div>
          <p className="font-medium">Fila de revisão vazia — tudo certo!</p>
          <p className="text-sm text-muted-foreground">
            Nenhum grupo aguardando revisão no momento.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
