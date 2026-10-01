/**
 * ImovelBuscaTypeahead — search box + live result rows over
 * `GET /api/imoveis/busca` (registry ∪ mirror, CONTRACT §0.1 / existing
 * `useImoveisBusca`).
 *
 * The list NARROWS as the código is typed (debounced, one round trip per
 * settle) until one is left; each result is a clickable row (photo, código,
 * endereço + complemento, R$). Clicking calls `onSelect` — what "select" means
 * (add interesse, add propriedade) belongs to the caller.
 *
 * `noc-organ-consume-check`: no typeahead organ exists in `@noctusai/lib`
 * (checked `components/**`); `MultiSelectPopover` is a fixed-option multi-select
 * over a list it already holds, not a debounced live fetch.
 *
 * Loading (lying-loading-state.md): `useImoveisBusca` keeps the PREVIOUS term's
 * rows on screen (`keepPreviousData`), so "no results" only renders when there
 * are genuinely none and nothing is in flight.
 */
import { useState } from "react";
import { Loader2, Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { useImoveisBusca } from "@/hooks/useCardHub";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import type { ImovelResumo } from "@/types/interesses";

import { ImovelLinhaInfo } from "./ImovelLinhaInfo";

export interface ImovelBuscaTypeaheadProps {
  onSelect: (imovel: ImovelResumo) => void;
  /** Códigos already on the target list — shown but not clickable. */
  jaNaLista?: string[];
  placeholder?: string;
  autoFocus?: boolean;
}

export function ImovelBuscaTypeahead({
  onSelect,
  jaNaLista = [],
  placeholder = "Digite o código do imóvel…",
  autoFocus,
}: ImovelBuscaTypeaheadProps) {
  const [termo, setTermo] = useState("");
  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useImoveisBusca(termoDebounced);

  const termoUtil = termoDebounced.trim().length >= 2;
  const resultados = (busca.data?.items ?? []) as ImovelResumo[];
  // `isPending` is true for a disabled query too — gate it on a useful term.
  const buscando = termoUtil && (busca.isPending || busca.isFetching);
  const jaSet = new Set(jaNaLista.map((c) => c.toUpperCase()));

  return (
    <div className="space-y-2" data-testid="imovel-busca-typeahead">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          placeholder={placeholder}
          className="pl-8"
          autoComplete="off"
          autoFocus={autoFocus}
          aria-label="Buscar imóvel pelo código"
          data-testid="imovel-busca-input"
        />
        {buscando && resultados.length > 0 && (
          <Loader2
            className="absolute right-2.5 top-2.5 h-4 w-4 animate-spin text-muted-foreground"
            data-testid="imovel-busca-atualizando"
          />
        )}
      </div>

      {termo.trim().length > 0 && (
        <div className="max-h-72 overflow-y-auto rounded-md border" data-testid="imovel-busca-resultados">
          {!termoUtil ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">Digite ao menos 2 caracteres.</p>
          ) : busca.isError ? (
            <p className="px-3 py-2 text-sm text-destructive" data-testid="imovel-busca-erro">
              Não foi possível buscar os imóveis.
            </p>
          ) : resultados.length === 0 ? (
            buscando ? (
              <p
                className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
                data-testid="imovel-busca-carregando"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando…
              </p>
            ) : (
              <p className="px-3 py-2 text-sm text-muted-foreground" data-testid="imovel-busca-vazio">
                Nenhum imóvel encontrado para “{termoDebounced.trim()}”.
              </p>
            )
          ) : (
            <ul>
              {resultados.map((row) => {
                const jaEsta = jaSet.has(row.codigo.toUpperCase());
                return (
                  <li key={row.codigo}>
                    <button
                      type="button"
                      disabled={jaEsta}
                      onClick={() => onSelect(row)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid={`imovel-busca-item-${row.codigo}`}
                    >
                      <ImovelLinhaInfo imovel={row} />
                      {jaEsta && <span className="shrink-0 text-xs">já na lista</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
