/**
 * CriarRoteiroDialog — compose a visiting route, in order.
 *
 * The flow the user described: type a ref (`ONE9`), watch the matches appear
 * live under the field, click the row, and the property joins the list. The
 * list is drag-and-drop, because the order IS the plan — "first this property,
 * then that one, and last this one".
 *
 * THE SEARCH REUSES `GET /api/imoveis?search=`
 * --------------------------------------------
 * That endpoint already `ilike`s `codigo` (`imoveis_service.list`), so `ONE9`
 * returns every `ONE9xxxx` with no new route. Checked before building: adding
 * a second search endpoint would have been a fork of a solved problem.
 *
 * NOT the seed's `MultiSelectPopover` (`noc-organ-consume-check`, run first).
 * That organ is a fixed-option multi-select over a list it already holds; this
 * is a debounced live-fetch typeahead whose result set is unbounded and whose
 * selections are ORDERED. The overlap is "a popover under a field" and nothing
 * else.
 *
 * Presentational (S3): `onCriar` is the only callback out; the caller owns the
 * POST and the toast.
 */
import { useMemo, useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useImoveisBusca } from "@/hooks/useCardHub";
import type { ImovelBusca, ImovelVisita, RoteiroCreateBody } from "@/types/cardHub";

import { ImovelVisitaCard } from "./ImovelVisitaCard";

/** A search hit, widened to the card's shape. The search endpoint returns the
 *  mirror row, which is by definition a listed imóvel — so `ativo_no_vista` is
 *  true and `fonte` is the mirror. The fields the card shows and the search
 *  does not return (captação, complemento) come back on the real `Visita`
 *  after the POST; here they are honestly null rather than guessed. */
function paraVisita(row: ImovelBusca): ImovelVisita {
  return {
    codigo: row.codigo,
    titulo: row.titulo ?? null,
    empreendimento: row.empreendimento ?? null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: row.bairro ?? null,
    cidade: row.cidade ?? null,
    uf: null,
    cep: null,
    foto_destaque: row.foto_destaque ?? null,
    captacao: null,
    corretores: [],
    ativo_no_vista: true,
    fonte: "imoveis",
  };
}

export interface CriarRoteiroDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCriar: (body: RoteiroCreateBody) => void;
  saving?: boolean;
}

export function CriarRoteiroDialog({
  open,
  onOpenChange,
  onCriar,
  saving,
}: CriarRoteiroDialogProps) {
  const [titulo, setTitulo] = useState("");
  const [termo, setTermo] = useState("");
  const [escolhidos, setEscolhidos] = useState<ImovelVisita[]>([]);

  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useImoveisBusca(termoDebounced);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const jaNoRoteiro = useMemo(
    () => new Set(escolhidos.map((i) => i.codigo.toUpperCase())),
    [escolhidos],
  );

  // 🔴 `isPending || isFetching`, never `isLoading`: v5's `isLoading` is false
  // during a background refetch, so an "nenhum imóvel" branch keyed off it
  // renders "no results" over results that exist.
  const buscando = busca.isPending || busca.isFetching;
  const termoUtil = termoDebounced.trim().length >= 2;
  const resultados = busca.data?.items ?? [];

  function adicionar(row: ImovelBusca) {
    if (jaNoRoteiro.has(row.codigo.toUpperCase())) return;
    setEscolhidos((atual) => [...atual, paraVisita(row)]);
    // The field clears but the popover stays open: a corretor adding three
    // properties types three refs in a row, and closing between them would
    // cost a click each time.
    setTermo("");
  }

  function remover(codigo: string) {
    setEscolhidos((atual) => atual.filter((i) => i.codigo !== codigo));
  }

  function aoSoltar(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setEscolhidos((atual) => {
      const de = atual.findIndex((i) => i.codigo === active.id);
      const para = atual.findIndex((i) => i.codigo === over.id);
      if (de < 0 || para < 0) return atual;
      return arrayMove(atual, de, para);
    });
  }

  function fechar(aberto: boolean) {
    if (!aberto) {
      setTitulo("");
      setTermo("");
      setEscolhidos([]);
    }
    onOpenChange(aberto);
  }

  function salvar() {
    if (!escolhidos.length) return;
    onCriar({
      titulo: titulo.trim() || null,
      // In list order — the array index becomes `visitas.ordem` server-side.
      imoveis: escolhidos.map((i) => i.codigo),
    });
  }

  return (
    <Dialog open={open} onOpenChange={fechar}>
      <DialogContent className="max-w-2xl" data-testid="criar-roteiro-dialog">
        <DialogHeader>
          <DialogTitle>Novo roteiro</DialogTitle>
          <DialogDescription>
            Busque os imóveis pela referência e arraste para definir a ordem da visita.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label
              className="mb-1 block text-xs font-medium text-muted-foreground"
              htmlFor="roteiro-titulo"
            >
              Título (opcional)
            </label>
            <Input
              id="roteiro-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Terça de manhã"
              data-testid="roteiro-titulo"
            />
          </div>

          <div className="relative">
            <label
              className="mb-1 block text-xs font-medium text-muted-foreground"
              htmlFor="roteiro-busca"
            >
              Buscar imóvel
            </label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                id="roteiro-busca"
                value={termo}
                onChange={(e) => setTermo(e.target.value)}
                placeholder="ONE9..."
                className="pl-8"
                autoComplete="off"
                data-testid="roteiro-busca"
              />
            </div>

            {termo.trim().length > 0 && (
              <div
                className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-popover shadow-md"
                data-testid="roteiro-busca-popover"
              >
                {!termoUtil ? (
                  <p className="px-3 py-2 text-sm text-muted-foreground">
                    Digite ao menos 2 caracteres.
                  </p>
                ) : buscando ? (
                  <p
                    className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
                    data-testid="roteiro-busca-carregando"
                  >
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando...
                  </p>
                ) : busca.isError ? (
                  <p className="px-3 py-2 text-sm text-destructive" data-testid="roteiro-busca-erro">
                    Não foi possível buscar os imóveis.
                  </p>
                ) : resultados.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-muted-foreground" data-testid="roteiro-busca-vazio">
                    Nenhum imóvel encontrado para “{termoDebounced.trim()}”.
                  </p>
                ) : (
                  <ul>
                    {resultados.map((row) => {
                      const jaEsta = jaNoRoteiro.has(row.codigo.toUpperCase());
                      return (
                        <li key={row.codigo}>
                          <button
                            type="button"
                            disabled={jaEsta}
                            onClick={() => adicionar(row)}
                            className="flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                            data-testid={`roteiro-busca-item-${row.codigo}`}
                          >
                            <span className="font-semibold">{row.codigo}</span>
                            <span className="truncate text-muted-foreground">
                              {[row.empreendimento ?? row.titulo, row.bairro]
                                .filter(Boolean)
                                .join(" · ")}
                            </span>
                            {jaEsta && (
                              <span className="ml-auto shrink-0 text-xs">já no roteiro</span>
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ordem da visita ({escolhidos.length})
            </p>
            {escolhidos.length === 0 ? (
              <p
                className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground"
                data-testid="roteiro-lista-vazia"
              >
                Nenhum imóvel adicionado ainda.
              </p>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={aoSoltar}
              >
                <SortableContext
                  items={escolhidos.map((i) => i.codigo)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-2" data-testid="roteiro-lista">
                    {escolhidos.map((imovel, i) => (
                      <ImovelVisitaCard
                        key={imovel.codigo}
                        id={imovel.codigo}
                        imovel={imovel}
                        posicao={i + 1}
                        onRemove={() => remover(imovel.codigo)}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => fechar(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button
            onClick={salvar}
            disabled={escolhidos.length === 0 || saving}
            data-testid="roteiro-salvar"
          >
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Criar roteiro
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
