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
 * 🔴 SECOND, INDEPENDENT AXIS — the "CPF" tab (`pessoa-mesma-cpf-multideal-
 * CONTRACT.md`, 2026-09-28). Same page, same two actions, but a SEPARATE
 * `GET /revisao-cpf` query family — see that file's §0 for why a card_hub
 * deal party can never surface on the identity tab above. `?tab=cpf` deep-
 * links straight into it (the card party "possível duplicata" badge points
 * here). The J/K/M/S keyboard shortcuts stay scoped to the identity tab —
 * the CPF tab's own survivor radio buttons would fight the same letters.
 *
 * Route: /clientes/revisao. Nav entry lives in BOTH NAV_GROUPS and
 * NAV_FALLBACK in App.tsx, and needs its own `status_pagina` row (backend
 * slice) — flagged in this slice's delivery note.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { RevisaoGrupoCard } from "@/components/clientes/RevisaoGrupoCard";
import { RevisaoCpfGrupoCard } from "@/components/clientes/RevisaoCpfGrupoCard";
import {
  DEFAULT_REVISAO_PAGE_SIZE,
  DEFAULT_REVISAO_CPF_PAGE_SIZE,
  useRevisaoFila,
  useRevisaoMutations,
  useRevisaoSegurosCount,
  useMergeSeguros,
  useRevisaoCpfFila,
  useRevisaoCpfMutations,
  type RevisaoGrupo,
} from "@/hooks/useClientesRevisao";

type RevisaoTab = "identidade" | "cpf";

export default function RevisaoFila() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<RevisaoTab>(
    searchParams.get("tab") === "cpf" ? "cpf" : "identidade",
  );

  function handleTabChange(next: string) {
    const nextTab = next === "cpf" ? "cpf" : "identidade";
    setTab(nextTab);
    // Keeps the URL shareable/refreshable without re-triggering this effect
    // as a navigation (replace, not push — switching tabs is not a "page").
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (nextTab === "cpf") p.set("tab", "cpf");
        else p.delete("tab");
        return p;
      },
      { replace: true },
    );
  }

  const [page, setPage] = useState(1);
  // Groups the operator has already acted on THIS session — filtered out of
  // the render immediately so a stale/cached page can never re-present one,
  // ahead of the invalidated query's refetch actually landing.
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());

  const filtros = { page, page_size: DEFAULT_REVISAO_PAGE_SIZE };
  const queue = useRevisaoFila(filtros);
  const { merge, manterSeparados, desfazer } = useRevisaoMutations();
  const seguros = useRevisaoSegurosCount();
  const mergeSeguros = useMergeSeguros();
  // Which card the keyboard is on. Index into the VISIBLE list, reset when
  // the page changes so the cursor never points past the end.
  const [cursor, setCursor] = useState(0);

  // ── CPF axis — independent page/resolved-set, same walkability rules ────
  const [cpfPage, setCpfPage] = useState(1);
  const [cpfResolvedIds, setCpfResolvedIds] = useState<Set<string>>(new Set());
  const cpfFiltros = { page: cpfPage, page_size: DEFAULT_REVISAO_CPF_PAGE_SIZE };
  const cpfQueue = useRevisaoCpfFila(cpfFiltros);
  const { merge: cpfMerge, manterSeparados: cpfManterSeparados } = useRevisaoCpfMutations();
  const cpfLoading = cpfQueue.isPending || cpfQueue.isFetching;
  const cpfData = cpfQueue.data;
  const cpfVisibleItems = (cpfData?.items ?? []).filter(
    (g) => !cpfResolvedIds.has(g.chave_canonica),
  );
  const cpfIsSuccessEmpty = !cpfLoading && !cpfQueue.isError && (cpfData?.total ?? 0) === 0;

  useEffect(() => {
    if (
      tab === "cpf" &&
      !cpfLoading &&
      cpfData &&
      cpfData.total > 0 &&
      cpfVisibleItems.length === 0 &&
      cpfData.items.length > 0 &&
      cpfPage < cpfData.pages
    ) {
      setCpfPage((p) => p + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, cpfLoading, cpfData, cpfVisibleItems.length, cpfPage]);

  function markCpfResolved(grupoId: string) {
    setCpfResolvedIds((prev) => new Set(prev).add(grupoId));
  }

  function handleCpfMerge(grupoId: string, sobreviventeId: string) {
    cpfMerge.mutate(
      { grupoId, clienteIdSobrevivente: sobreviventeId },
      {
        onSuccess: () => {
          markCpfResolved(grupoId);
          toast.success("Cadastros unificados.", {
            description: "Todas as negociações e documentos ficaram no cadastro escolhido.",
          });
        },
        onError: (err) =>
          toast.error("Erro ao unificar os cadastros.", {
            description: err instanceof Error ? err.message : undefined,
          }),
      },
    );
  }

  function handleCpfManterSeparados(grupoId: string) {
    cpfManterSeparados.mutate(grupoId, {
      onSuccess: () => {
        markCpfResolved(grupoId);
        toast.success("Mantidos separados.", {
          description: "Este CPF não vai mais aparecer nesta fila.",
        });
      },
      onError: (err) =>
        toast.error("Erro ao salvar a decisão.", {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
  }

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

  useEffect(() => {
    setCursor(0);
  }, [page]);

  // 🔴 KEYBOARD FIRST, BECAUSE THE QUEUE IS LONG.
  //
  // 351 groups at two mouse trips each is why this queue was never drained.
  // J/K move, M merges, S keeps separate — the same letters the operator is
  // already saying out loud ("mesclar", "separar"). Ignored while focus is in
  // a field, so typing never triggers a merge.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const alvo = e.target as HTMLElement | null;
      const digitando =
        alvo &&
        (alvo.tagName === "INPUT" ||
          alvo.tagName === "TEXTAREA" ||
          alvo.isContentEditable);
      if (digitando || e.metaKey || e.ctrlKey || e.altKey) return;
      // Scoped to the identity tab — the CPF tab has its own survivor radio
      // buttons per candidate, which these same letters would otherwise fight.
      if (tab !== "identidade") return;
      if (!visibleItems.length) return;

      const atual = visibleItems[Math.min(cursor, visibleItems.length - 1)];
      switch (e.key.toLowerCase()) {
        case "j":
        case "arrowdown":
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, visibleItems.length - 1));
          break;
        case "k":
        case "arrowup":
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          break;
        case "m":
          e.preventDefault();
          if (atual) handleMerge(atual);
          break;
        case "s":
          e.preventDefault();
          if (atual) handleManterSeparados(atual);
          break;
        default:
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, visibleItems, cursor]);

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

  function handleMergeSeguros() {
    mergeSeguros.mutate(undefined, {
      onSuccess: (r) => {
        setResolvedIds(new Set());
        setPage(1);
        toast.success(
          `${r.grupos_mesclados} grupo(s) mesclado(s).`,
          {
            description: `${r.clientes_absorvidos} cadastro(s) unidos. ${r.grupos_restantes} grupo(s) seguem aguardando decisão.`,
            duration: 10000,
          },
        );
      },
      onError: (err) =>
        toast.error("Não foi possível mesclar os grupos.", {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
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
          {tab === "identidade"
            ? data
              ? `${data.total.toLocaleString("pt-BR")} grupo(s) aguardando revisão.`
              : "Carregando…"
            : cpfData
              ? `${cpfData.total.toLocaleString("pt-BR")} grupo(s) de CPF aguardando revisão.`
              : "Carregando…"}
        </p>
        {tab === "identidade" && (
          <p className="mt-1 text-xs text-muted-foreground">
            Teclado: <kbd className="rounded border px-1">J</kbd>/
            <kbd className="rounded border px-1">K</kbd> navega ·{" "}
            <kbd className="rounded border px-1">M</kbd> mescla ·{" "}
            <kbd className="rounded border px-1">S</kbd> mantém separados
          </p>
        )}
      </div>

      <Tabs value={tab} onValueChange={handleTabChange}>
        <TabsList data-testid="revisao-tabs">
          <TabsTrigger value="identidade" data-testid="revisao-tab-identidade">
            Identidade
          </TabsTrigger>
          <TabsTrigger value="cpf" data-testid="revisao-tab-cpf">
            CPF
          </TabsTrigger>
        </TabsList>

        <TabsContent value="identidade" className="space-y-4 pt-4">
          {!queue.isError && (seguros.data?.grupos_mesclados ?? 0) > 0 && (
            <Card
              className="border-primary/30 bg-primary/5"
              data-testid="revisao-seguros-banner"
            >
              <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
                <div>
                  <p className="font-medium">
                    {seguros.data!.grupos_mesclados.toLocaleString("pt-BR")} grupo(s)
                    sem ambiguidade
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Mesmo nome com pontuação, marcador de origem ou apelido de rede
                    social. Cada mesclagem pode ser desfeita.
                  </p>
                </div>
                <Button
                  onClick={handleMergeSeguros}
                  disabled={mergeSeguros.isPending}
                  data-testid="revisao-merge-seguros-btn"
                >
                  {mergeSeguros.isPending
                    ? "Mesclando…"
                    : `Mesclar ${seguros.data!.grupos_mesclados} grupo(s)`}
                </Button>
              </CardContent>
            </Card>
          )}

          {queue.isError ? (
            <ErrorState onRetry={() => queue.refetch()} />
          ) : loading && !data ? (
            <LoadingState />
          ) : isSuccessEmpty ? (
            <SuccessEmptyState />
          ) : (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                {visibleItems.map((grupo, i) => (
                  <div
                    key={grupo.chave_canonica}
                    className={
                      i === Math.min(cursor, visibleItems.length - 1)
                        ? "rounded-lg ring-2 ring-primary ring-offset-2 ring-offset-background"
                        : undefined
                    }
                    data-testid={
                      i === Math.min(cursor, visibleItems.length - 1)
                        ? "revisao-cursor"
                        : undefined
                    }
                  >
                  <RevisaoGrupoCard
                    grupo={grupo}
                    onMerge={handleMerge}
                    onManterSeparados={handleManterSeparados}
                    merging={merge.isPending && merge.variables?.grupoId === grupo.chave_canonica}
                    rejecting={
                      manterSeparados.isPending && manterSeparados.variables === grupo.chave_canonica
                    }
                  />
                  </div>
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
        </TabsContent>

        <TabsContent value="cpf" className="space-y-4 pt-4">
          <p className="text-xs text-muted-foreground">
            A mesma pessoa apareceu em negociações diferentes com o mesmo CPF —
            por exemplo, vendedora de um imóvel e compradora de outro.
          </p>

          {cpfQueue.isError ? (
            <ErrorState onRetry={() => cpfQueue.refetch()} />
          ) : cpfLoading && !cpfData ? (
            <LoadingState />
          ) : cpfIsSuccessEmpty ? (
            <SuccessEmptyState />
          ) : (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                {cpfVisibleItems.map((grupo) => (
                  <RevisaoCpfGrupoCard
                    key={grupo.chave_canonica}
                    grupo={grupo}
                    onMerge={handleCpfMerge}
                    onManterSeparados={handleCpfManterSeparados}
                    merging={
                      cpfMerge.isPending && cpfMerge.variables?.grupoId === grupo.chave_canonica
                    }
                    rejecting={
                      cpfManterSeparados.isPending &&
                      cpfManterSeparados.variables === grupo.chave_canonica
                    }
                  />
                ))}
              </div>

              {cpfData && cpfData.pages > 1 && (
                <div className="flex items-center justify-center gap-3 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cpfData.page <= 1}
                    onClick={() => setCpfPage((p) => Math.max(1, p - 1))}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Página {cpfData.page} de {cpfData.pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cpfData.page >= cpfData.pages}
                    onClick={() => setCpfPage((p) => p + 1)}
                  >
                    Próxima
                  </Button>
                </div>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
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
