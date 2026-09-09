/**
 * ImovelCodigoPicker — pick ONE imóvel, by código or by what it is called.
 *
 * 🔴 REGISTRY-BACKED, which is the entire reason it exists. It searches
 * `GET /api/imoveis/busca` (registry ∪ mirror), so a property that has left
 * the Vista catalog is findable. That matters here more than anywhere else in
 * the product: this picker names the imóvel of a NEGOCIAÇÃO, and an imóvel
 * leaves the catalog *because it was sold* — the mirror-only search could not
 * offer the one property a closing deal is about.
 *
 * NOT a canonical organ (`noc-organ-consume-check`, run first). `@noctusai/lib`
 * ships `MultiSelectPopover`, a fixed-option multi-select over a list it
 * already holds; this is a single-value debounced live-fetch typeahead over an
 * unbounded result set. The overlap is "a popover under a field".
 *
 * WHY IT DOES NOT SHARE CODE WITH `CriarRoteiroDialog`'s TYPEAHEAD (N=2, and
 * triaged rather than reflexively merged): the two share the part that carries
 * the real logic — `useImoveisBusca`, one hook, one endpoint, one debounce
 * contract — and differ in everything around it. That one composes an ORDERED
 * MULTI-selection with drag-and-drop and keeps its popover open across picks;
 * this one holds a single value and closes on choice. Fusing them would mean a
 * component with a `multiple` flag branching in five places, which is the
 * shape DRY is supposed to prevent rather than produce.
 *
 * Presentational-with-its-own-query (the same seam `CriarRoteiroDialog` uses):
 * value in, `onChange` out.
 */
import { useState } from "react";
import { Check, Loader2, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useImoveisBusca } from "@/hooks/useCardHub";
import { cn } from "@/lib/utils";
import type { ImovelBusca } from "@/types/cardHub";

export interface ImovelCodigoPickerProps {
  /** The canonical código currently chosen, or `null`/`""` for none. */
  value: string | null;
  onChange: (codigo: string | null) => void;
  disabled?: boolean;
  id?: string;
  "data-testid"?: string;
}

/** `ONE9001 — Apartamento amplo · Pinheiros`, skipping what is unknown. */
export function rotuloDoImovel(imovel: ImovelBusca): string {
  const detalhe = [imovel.titulo, imovel.bairro].filter(Boolean).join(" · ");
  return detalhe ? `${imovel.codigo} — ${detalhe}` : imovel.codigo;
}

export function ImovelCodigoPicker({
  value,
  onChange,
  disabled,
  id,
  "data-testid": testId = "imovel-picker",
}: ImovelCodigoPickerProps) {
  const [termo, setTermo] = useState("");
  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useImoveisBusca(termoDebounced);

  // 🔴 `isPending || isFetching`, never `isLoading`: v5's `isLoading` is false
  // during a background refetch, so a "nenhum imóvel" branch keyed off it
  // renders "no results" over results that exist. `keepPreviousData` in the
  // hook keeps the previous term's list on screen meanwhile.
  const buscando = busca.isPending || busca.isFetching;
  const termoUtil = termoDebounced.trim().length >= 2;
  const resultados = busca.data?.items ?? [];

  if (value) {
    return (
      <div
        className="flex items-center gap-2 rounded-md border px-3 py-2"
        data-testid={`${testId}-escolhido`}
      >
        <Check className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm font-medium tabular-nums">
          {value}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={disabled}
          onClick={() => {
            onChange(null);
            setTermo("");
          }}
          aria-label="Remover o imóvel da negociação"
          data-testid={`${testId}-limpar`}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5" data-testid={testId}>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          id={id}
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          placeholder="Buscar por código, título ou bairro..."
          className="pl-8"
          disabled={disabled}
          autoComplete="off"
          data-testid={`${testId}-input`}
        />
        {buscando && termoUtil && (
          <Loader2
            className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground"
            data-testid={`${testId}-buscando`}
          />
        )}
      </div>

      {!termoUtil ? (
        <p className="text-xs text-muted-foreground">
          Digite ao menos 2 caracteres.
        </p>
      ) : resultados.length === 0 && !buscando ? (
        <p className="text-xs text-muted-foreground" data-testid={`${testId}-vazio`}>
          Nenhum imóvel encontrado para “{termoDebounced.trim()}”.
        </p>
      ) : (
        <ul className="max-h-56 divide-y overflow-y-auto rounded-md border">
          {resultados.map((imovel) => (
            <li key={imovel.codigo}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
                disabled={disabled}
                onClick={() => {
                  onChange(imovel.codigo);
                  setTermo("");
                }}
                data-testid={`${testId}-opcao-${imovel.codigo}`}
              >
                <span className="min-w-0 flex-1 truncate">
                  {rotuloDoImovel(imovel)}
                </span>
                {!imovel.ativo_no_vista && (
                  // 🔴 Labelled, never filtered out. A sold imóvel is the
                  // RIGHT answer on a closing deal — but the operator has to
                  // see which of two similar códigos is the live listing.
                  <span
                    className={cn(
                      "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
                      "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
                    )}
                  >
                    fora do catálogo
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
