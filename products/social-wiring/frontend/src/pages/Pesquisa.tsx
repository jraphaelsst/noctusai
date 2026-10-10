/**
 * Minha Pesquisa (`/media-creation/pesquisa`) — per-marca research items the
 * headline/roteiro generators draw from. Contract:
 * projects/core-studio/specs/pesquisa-contract.md §4.
 *
 * - manual add = approved; AI-classified = pending (Aprovar / Rejeitar);
 *   rejected is soft and never listed.
 * - Loading: two signals off `data` (`showSkeleton` / `isRefreshing`), never
 *   `.isLoading` (lying-loading-state.md); filter/brand key changes keep the
 *   previous list via `placeholderData`.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AssuntosVirais } from "@/components/pesquisa/AssuntosVirais";
import { AdicionarItensModal } from "@/components/pesquisa/AdicionarItensModal";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import { GRUPO_ROTULO } from "@/components/pesquisa/labels";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { VariavelSelect } from "@/components/pesquisa/VariavelSelect";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import {
  useAcaoEmMassa,
  useAprovarItem,
  useExcluirItem,
  usePesquisaCounts,
  usePesquisaItens,
  usePesquisaVariaveis,
  useRejeitarItem,
  useZerarPesquisa,
  type PesquisaItem,
  type PesquisaSort,
  type PesquisaStatus,
  type PesquisaVariable,
} from "@/hooks/usePesquisa";

const PAGE_SIZE = 50;
const GROUPED_PAGE_SIZE = 200;
const BULK_CHUNK = 500;

type PesquisaTab = "itens" | "assuntos-virais";

type ConfirmAcao =
  | { tipo: "excluir-item"; item: PesquisaItem }
  | { tipo: "excluir-selecionados" }
  | { tipo: "zerar" };

export default function Pesquisa() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const {
    marcaId,
    marca,
    escolherMarca: salvarEscolha,
  } = useMarcaPesquisa(marcas);

  const [searchParams, setSearchParams] = useSearchParams();
  const tab: PesquisaTab =
    searchParams.get("tab") === "assuntos-virais" ? "assuntos-virais" : "itens";
  const [status, setStatus] = useState<PesquisaStatus>(
    searchParams.get("status") === "pending" ? "pending" : "approved",
  );
  const [sort, setSort] = useState<PesquisaSort>("recent");
  const [variavel, setVariavel] = useState("");
  const [agrupar, setAgrupar] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [adicionarAberto, setAdicionarAberto] = useState(false);
  const [acoesAberto, setAcoesAberto] = useState(false);
  const [confirmar, setConfirmar] = useState<ConfirmAcao | null>(null);

  const variaveisQ = usePesquisaVariaveis();
  const variaveis = variaveisQ.data ?? [];
  const variavelPorSlug = useMemo(
    () => new Map(variaveis.map((v) => [v.slug, v])),
    [variaveis],
  );

  const countsQ = usePesquisaCounts(marcaId);
  const itensQ = usePesquisaItens({
    marcaId,
    status,
    variableSlug: variavel || null,
    sort,
    pageSize: agrupar ? GROUPED_PAGE_SIZE : PAGE_SIZE,
  });
  const { items, total } = itensQ;

  const aprovar = useAprovarItem();
  const rejeitar = useRejeitarItem();
  const excluir = useExcluirItem();
  const emMassa = useAcaoEmMassa();
  const zerar = useZerarPesquisa();

  // Selection never outlives the view it was made in.
  useEffect(() => {
    setSelecionados(new Set());
  }, [marcaId, status, variavel, sort, agrupar]);

  function escolherMarca(id: string) {
    salvarEscolha(id);
    setVariavel("");
  }

  function trocarAba(next: string) {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("tab", next === "assuntos-virais" ? "assuntos-virais" : "itens");
        return p;
      },
      { replace: true },
    );
  }

  function alternar(id: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const todosSelecionados =
    items.length > 0 && items.every((i) => selecionados.has(i.id));

  async function executarEmMassa(action: "approve" | "delete") {
    if (!marcaId) return;
    const ids = [...selecionados];
    try {
      let afetados = 0;
      for (let i = 0; i < ids.length; i += BULK_CHUNK) {
        const r = await emMassa.mutateAsync({
          marca_id: marcaId,
          action,
          ids: ids.slice(i, i + BULK_CHUNK),
        });
        afetados += r.affected;
      }
      toast.success(
        action === "approve"
          ? `${afetados} item(ns) aprovado(s).`
          : `${afetados} item(ns) excluído(s).`,
      );
      setSelecionados(new Set());
    } catch {
      toast.error("Não foi possível concluir a ação em massa.");
    } finally {
      setConfirmar(null);
      setAcoesAberto(false);
    }
  }

  async function executarConfirmacao() {
    if (!confirmar || !marcaId) return;
    if (confirmar.tipo === "excluir-selecionados")
      return executarEmMassa("delete");
    try {
      if (confirmar.tipo === "excluir-item") {
        await excluir.mutateAsync(confirmar.item.id);
        toast.success("Item excluído.");
      } else {
        const r = await zerar.mutateAsync(marcaId);
        toast.success(`${r.deleted} item(ns) removido(s). Pesquisa zerada.`);
        setSelecionados(new Set());
        setAcoesAberto(false);
      }
    } catch {
      toast.error("Não foi possível concluir a exclusão.");
    } finally {
      setConfirmar(null);
    }
  }

  async function decidir(item: PesquisaItem, acao: "aprovar" | "rejeitar") {
    try {
      if (acao === "aprovar") await aprovar.mutateAsync(item.id);
      else await rejeitar.mutateAsync(item.id);
      toast.success(acao === "aprovar" ? "Item aprovado." : "Item rejeitado.");
    } catch {
      toast.error("Não foi possível atualizar o item.");
    }
  }

  const contagens = countsQ.data;
  const confirmando = excluir.isPending || zerar.isPending || emMassa.isPending;

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Minha Pesquisa</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as variáveis de pesquisa de cada marca para criar headlines
            inteligentes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <MarcaSwitcher
            marcas={marcas}
            marcaId={marcaId}
            onChange={escolherMarca}
          />
          <Button asChild variant="outline">
            <Link to="/media-creation/pesquisa/extrair">
              <Sparkles className="mr-1.5 h-4 w-4" />
              Extrair Pesquisa
            </Link>
          </Button>
          {tab === "itens" && (
            <Button
              onClick={() => setAdicionarAberto(true)}
              disabled={!marcaId}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Adicionar itens
            </Button>
          )}
        </div>
      </header>

      {marcasQ.isPending && !marcasQ.data ? (
        <Skeleton className="h-40 w-full" />
      ) : marcasQ.isError && !marcasQ.data ? (
        <ErroBloco
          onRetry={() => void marcasQ.refetch()}
          texto="Não foi possível carregar as marcas."
        />
      ) : !marcaId ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Cadastre uma marca em Clientes para começar sua pesquisa.
        </p>
      ) : (
        <>
          <Tabs value={tab} onValueChange={trocarAba}>
            <TabsList>
              <TabsTrigger value="itens">Itens de pesquisa</TabsTrigger>
              <TabsTrigger value="assuntos-virais">Assuntos virais</TabsTrigger>
            </TabsList>
          </Tabs>
          {tab === "assuntos-virais" ? (
            <AssuntosVirais marcaId={marcaId} />
          ) : (
            <>
              <div
                className="flex flex-wrap items-center gap-3"
                role="toolbar"
                aria-label="Filtros"
              >
                <select
                  aria-label="Ordenar"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as PesquisaSort)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm"
                >
                  <option value="recent">Mais recentes</option>
                  <option value="plays">Mais views</option>
                </select>
                <div
                  className="inline-flex rounded-md border"
                  role="group"
                  aria-label="Status"
                >
                  <Button
                    size="sm"
                    variant={status === "approved" ? "default" : "ghost"}
                    onClick={() => setStatus("approved")}
                  >
                    Aprovados ({contagens?.approved ?? 0})
                  </Button>
                  <Button
                    size="sm"
                    variant={status === "pending" ? "default" : "ghost"}
                    onClick={() => setStatus("pending")}
                  >
                    Pendentes ({contagens?.pending ?? 0})
                  </Button>
                </div>
                <VariavelSelect
                  ariaLabel="Variável"
                  value={variavel}
                  onChange={setVariavel}
                  variaveis={variaveis}
                  vazioRotulo="Todas as variáveis"
                />
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    aria-label="Agrupar"
                    checked={agrupar}
                    onCheckedChange={(c) => setAgrupar(c === true)}
                  />
                  Agrupar
                </label>
                <span className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
                  {itensQ.isRefreshing && (
                    <span role="status" className="flex items-center gap-1">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Atualizando…
                    </span>
                  )}
                  {total} {total === 1 ? "item" : "itens"}
                </span>
              </div>

              {selecionados.size > 0 && (
                <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 px-4 py-2 text-sm">
                  <span>
                    {selecionados.size} selecionado
                    {selecionados.size === 1 ? "" : "s"}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setSelecionados(new Set(items.map((i) => i.id)))
                    }
                  >
                    Selecionar todos
                  </Button>
                  <Button size="sm" onClick={() => setAcoesAberto(true)}>
                    Ações
                  </Button>
                </div>
              )}

              {itensQ.showSkeleton ? (
                <div
                  className="space-y-2"
                  aria-busy="true"
                  data-testid="pesquisa-skeleton"
                >
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : itensQ.isError && !itensQ.data ? (
                <ErroBloco
                  onRetry={() => void itensQ.refetch()}
                  texto="Não foi possível carregar a pesquisa."
                />
              ) : items.length === 0 ? (
                <p className="py-16 text-center text-sm text-muted-foreground">
                  Nenhum item encontrado.
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 px-1 text-sm text-muted-foreground">
                    <Checkbox
                      aria-label="Selecionar todos os itens da lista"
                      checked={todosSelecionados}
                      onCheckedChange={(c) =>
                        setSelecionados(
                          c === true
                            ? new Set(items.map((i) => i.id))
                            : new Set(),
                        )
                      }
                    />
                    Selecionar itens
                  </div>
                  {agrupar ? (
                    agruparItens(items, variaveis).map(
                      ({ slug, rotulo, itens }) => (
                        <section key={slug} className="space-y-2">
                          <h2 className="text-sm font-semibold">
                            {rotulo}{" "}
                            <span className="font-normal text-muted-foreground">
                              ({itens.length})
                            </span>
                          </h2>
                          {itens.map((it) => (
                            <LinhaItem
                              key={it.id}
                              item={it}
                              variavel={variavelPorSlug.get(it.variable_slug)}
                              selecionado={selecionados.has(it.id)}
                              onToggle={() => alternar(it.id)}
                              onAprovar={() => void decidir(it, "aprovar")}
                              onRejeitar={() => void decidir(it, "rejeitar")}
                              onExcluir={() =>
                                setConfirmar({ tipo: "excluir-item", item: it })
                              }
                            />
                          ))}
                        </section>
                      ),
                    )
                  ) : (
                    <div className="space-y-2">
                      {items.map((it) => (
                        <LinhaItem
                          key={it.id}
                          item={it}
                          variavel={variavelPorSlug.get(it.variable_slug)}
                          selecionado={selecionados.has(it.id)}
                          onToggle={() => alternar(it.id)}
                          onAprovar={() => void decidir(it, "aprovar")}
                          onRejeitar={() => void decidir(it, "rejeitar")}
                          onExcluir={() =>
                            setConfirmar({ tipo: "excluir-item", item: it })
                          }
                        />
                      ))}
                    </div>
                  )}
                  {!agrupar && itensQ.hasNextPage && (
                    <div className="flex justify-center">
                      <Button
                        variant="outline"
                        disabled={itensQ.isFetchingNextPage}
                        onClick={() => void itensQ.fetchNextPage()}
                      >
                        {itensQ.isFetchingNextPage
                          ? "Carregando…"
                          : "Carregar mais"}
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}

      {marcaId && tab === "itens" && (
        <AdicionarItensModal
          open={adicionarAberto}
          onOpenChange={setAdicionarAberto}
          marcaId={marcaId}
          variaveis={variaveis}
          variavelInicial={variavel}
        />
      )}

      <Dialog open={acoesAberto} onOpenChange={setAcoesAberto}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Ações</DialogTitle>
            <DialogDescription>
              {selecionados.size} item(ns) selecionado(s) em {marca?.name}.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {status === "pending" && (
              <Button
                variant="outline"
                disabled={emMassa.isPending || selecionados.size === 0}
                onClick={() => void executarEmMassa("approve")}
              >
                Aprovar
              </Button>
            )}
            <Button
              variant="outline"
              disabled={selecionados.size === 0}
              onClick={() => setConfirmar({ tipo: "excluir-selecionados" })}
            >
              Excluir selecionados
            </Button>
            <Button
              variant="destructive"
              onClick={() => setConfirmar({ tipo: "zerar" })}
            >
              Zerar toda a pesquisa da marca
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmarModal
        open={confirmar !== null}
        onOpenChange={(o) => !o && setConfirmar(null)}
        pendente={confirmando}
        titulo={
          confirmar?.tipo === "zerar"
            ? "Zerar toda a pesquisa da marca?"
            : confirmar?.tipo === "excluir-selecionados"
              ? "Excluir itens selecionados?"
              : "Excluir item?"
        }
        descricao={
          confirmar?.tipo === "zerar"
            ? `Todos os itens (aprovados e pendentes) de ${marca?.name ?? "esta marca"} serão apagados. Esta ação não pode ser desfeita.`
            : confirmar?.tipo === "excluir-selecionados"
              ? `${selecionados.size} item(ns) serão apagados. Esta ação não pode ser desfeita.`
              : "O item será removido da pesquisa. Esta ação não pode ser desfeita."
        }
        rotuloConfirmar={
          confirmar?.tipo === "zerar" ? "Zerar pesquisa" : "Excluir"
        }
        digitarPara={confirmar?.tipo === "zerar" ? marca?.name : undefined}
        onConfirmar={() => void executarConfirmacao()}
      />
    </div>
  );
}

function agruparItens(items: PesquisaItem[], variaveis: PesquisaVariable[]) {
  const ordem = new Map(variaveis.map((v) => [v.slug, v.sort_order]));
  const porSlug = new Map<string, PesquisaItem[]>();
  for (const it of items)
    porSlug.set(it.variable_slug, [
      ...(porSlug.get(it.variable_slug) ?? []),
      it,
    ]);
  return [...porSlug.entries()]
    .sort(([a], [b]) => (ordem.get(a) ?? 999) - (ordem.get(b) ?? 999))
    .map(([slug, itens]) => ({
      slug,
      rotulo: variaveis.find((v) => v.slug === slug)?.label ?? slug,
      itens,
    }));
}

function ErroBloco({ texto, onRetry }: { texto: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 py-16 text-sm"
    >
      <AlertCircle className="h-6 w-6 text-destructive" />
      {texto}
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Tentar novamente
      </Button>
    </div>
  );
}

interface LinhaProps {
  item: PesquisaItem;
  variavel: PesquisaVariable | undefined;
  selecionado: boolean;
  onToggle: () => void;
  onAprovar: () => void;
  onRejeitar: () => void;
  onExcluir: () => void;
}

function LinhaItem({
  item,
  variavel,
  selecionado,
  onToggle,
  onAprovar,
  onRejeitar,
  onExcluir,
}: LinhaProps) {
  const meta = [
    variavel?.label ?? item.variable_slug,
    variavel ? GRUPO_ROTULO[variavel.grupo] : null,
    item.origin === "manual"
      ? "manual"
      : item.origin === "ai_classified"
        ? "IA"
        : item.origin === "extraction"
          ? "extração"
          : null,
    item.plays != null ? `${item.plays.toLocaleString("pt-BR")} views` : null,
  ].filter(Boolean);
  const verPost = item.source_ref?.url ?? null;
  const pendente = item.status === "pending";
  return (
    <div
      className="flex items-center gap-3 overflow-hidden rounded-md border bg-card pr-3"
      data-testid="pesquisa-linha"
    >
      <div
        className={`self-stretch w-1 ${pendente ? "bg-orange-500" : "bg-purple-500"}`}
        aria-hidden
      />
      <Checkbox
        aria-label={`Selecionar: ${item.content}`}
        checked={selecionado}
        onCheckedChange={onToggle}
      />
      <div className="min-w-0 flex-1 py-3">
        <p className="break-words text-sm">{item.content}</p>
        <p className="text-xs text-muted-foreground">{meta.join(" · ")}</p>
      </div>
      {verPost && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <a
                href={verPost}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Ver post"
                title={item.source_ref?.excerpt ?? undefined}
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                Ver post <ExternalLink className="h-3 w-3" aria-hidden />
              </a>
            </TooltipTrigger>
            {item.source_ref?.excerpt && (
              <TooltipContent className="max-w-xs">
                {item.source_ref.excerpt}
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      )}
      {pendente ? (
        <div className="flex gap-2">
          <Badge variant="secondary">Pendente</Badge>
          <Button size="sm" onClick={onAprovar}>
            Aprovar
          </Button>
          <Button size="sm" variant="outline" onClick={onRejeitar}>
            Rejeitar
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="ghost" onClick={onExcluir}>
          Excluir
        </Button>
      )}
    </div>
  );
}
