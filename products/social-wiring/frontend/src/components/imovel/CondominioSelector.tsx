/**
 * CondominioSelector — the imóvel's condomínio answer (migration 300, owner
 * decision 2026-10-21): attach the property to ONE condomínio of the master
 * list, or check "Casa de rua (fora de condomínio)". Neither = not answered
 * (the contract readiness asks for it) — never a silent "não".
 *
 * Controlled: `value` + `onChange`; persisting is the caller's form
 * (`ImovelCartorioCard` "Salvar", `ImovelManualModal` "Salvar"). The search
 * fetches as the user types (debounced) and lists clickable items under the
 * field; the last item creates a condomínio with the typed name and attaches
 * it (the server dedupes by normalised name — an existing one comes back).
 *
 * `noc-organ-consume-check`: `@noctusai/lib` ships no typeahead organ (same
 * finding as `ImovelBuscaTypeahead`); this mirrors that component's shape.
 * Loading (lying-loading-state.md): `useCondominioBusca` keeps the previous
 * term's items (`placeholderData`), so "nenhum encontrado" only renders when
 * nothing is in flight and there are genuinely none.
 *
 * The wrapper's id (default `imovel-condominio`) is the readiness falta's
 * `destino.alvo` — `derivacao.ALVO_CONDOMINIO_DO_IMOVEL`.
 */
import { useState } from "react";
import { Building2, Loader2, Plus, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  type CondominioResumo,
  useCondominioBusca,
  useCriarCondominio,
} from "@/hooks/useCondominios";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

export interface CondominioValor {
  condominio: CondominioResumo | null;
  casaDeRua: boolean;
}

interface Props {
  value: CondominioValor;
  onChange: (v: CondominioValor) => void;
  disabled?: boolean;
  /** DOM id of the wrapper (the readiness "Resolver" target). */
  id?: string;
  /** The pre-300 free flag said "em condomínio" — nudge to attach one. */
  legadoEmCondominio?: boolean | null;
}

export default function CondominioSelector({
  value,
  onChange,
  disabled,
  id = "imovel-condominio",
  legadoEmCondominio,
}: Props) {
  const [termo, setTermo] = useState("");
  const [trocando, setTrocando] = useState(false);
  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useCondominioBusca(termoDebounced);
  const criar = useCriarCondominio();

  const textoDigitado = termo.trim();
  const termoUtil = termoDebounced.trim().length > 0;
  const resultados = termoUtil ? (busca.data ?? []) : [];
  // Two signals, never `isLoading` (lying-loading-state).
  const mostrarCarregando = termoUtil && busca.isPending && !busca.data;
  const atualizando = termoUtil && busca.isFetching && !!busca.data;
  const mostrarBusca = !value.casaDeRua && (!value.condominio || trocando);

  function anexar(c: CondominioResumo) {
    onChange({ condominio: c, casaDeRua: false });
    setTermo("");
    setTrocando(false);
  }

  function cadastrar() {
    if (!textoDigitado) return;
    criar.mutate({ nome: textoDigitado }, { onSuccess: (c) => anexar(c) });
  }

  return (
    <div id={id} className="space-y-2" data-testid="imovel-condominio">
      <Label>Condomínio</Label>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={value.casaDeRua}
          onCheckedChange={(v) => {
            onChange({ condominio: null, casaDeRua: v === true });
            setTrocando(false);
          }}
          disabled={disabled}
          data-testid="imovel-casa-de-rua"
          aria-label="Casa de rua (fora de condomínio)"
        />
        Casa de rua (fora de condomínio)
      </label>

      {!value.casaDeRua && value.condominio && (
        <div className="flex flex-wrap items-center gap-2" data-testid="imovel-condominio-chip">
          <Badge variant="secondary" className="gap-1 py-1 text-sm">
            <Building2 className="h-3.5 w-3.5" />
            {value.condominio.nome}
            {value.condominio.cidade ? ` · ${value.condominio.cidade}` : ""}
          </Badge>
          {value.condominio.status_validacao === "sugerido" && (
            <span className="text-xs text-muted-foreground">aguardando validação</span>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setTrocando((t) => !t)}
            disabled={disabled}
            data-testid="imovel-condominio-trocar"
          >
            {trocando ? "Cancelar troca" : "Trocar"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange({ condominio: null, casaDeRua: false });
              setTrocando(false);
            }}
            disabled={disabled}
            data-testid="imovel-condominio-remover"
          >
            <X className="mr-1 h-3.5 w-3.5" />
            Remover
          </Button>
        </div>
      )}

      {mostrarBusca && (
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            placeholder="Digite o nome do condomínio…"
            className="pl-8"
            autoComplete="off"
            disabled={disabled}
            aria-label="Buscar condomínio pelo nome"
            data-testid="imovel-condominio-busca"
          />
          {atualizando && (
            <Loader2
              className="absolute right-2.5 top-2.5 h-4 w-4 animate-spin text-muted-foreground"
              data-testid="imovel-condominio-atualizando"
            />
          )}
          {textoDigitado.length > 0 && (
            <div
              className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-popover shadow-md"
              role="listbox"
              data-testid="imovel-condominio-resultados"
            >
              {busca.isError ? (
                <p className="px-3 py-2 text-sm text-destructive" data-testid="imovel-condominio-erro">
                  Não foi possível buscar os condomínios.
                </p>
              ) : mostrarCarregando ? (
                <p
                  className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
                  data-testid="imovel-condominio-carregando"
                >
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando…
                </p>
              ) : (
                <ul>
                  {resultados.length === 0 && termoUtil && !busca.isFetching && (
                    <li className="px-3 py-2 text-sm text-muted-foreground" data-testid="imovel-condominio-vazio">
                      Nenhum condomínio encontrado.
                    </li>
                  )}
                  {resultados.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={value.condominio?.id === c.id}
                        onClick={() => anexar(c)}
                        disabled={disabled}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                        data-testid={`imovel-condominio-item-${c.id}`}
                      >
                        <Building2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <span className="truncate">{c.nome}</span>
                        {(c.bairro || c.cidade) && (
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                            {[c.bairro, c.cidade].filter(Boolean).join(", ")}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                  <li className="border-t">
                    <button
                      type="button"
                      onClick={cadastrar}
                      disabled={disabled || criar.isPending}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-accent disabled:opacity-60"
                      data-testid="imovel-condominio-cadastrar"
                    >
                      {criar.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Plus className="h-3.5 w-3.5" />
                      )}
                      Cadastrar condomínio “{textoDigitado}”
                    </button>
                  </li>
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {criar.isError && (
        <p className="text-sm text-destructive" data-testid="imovel-condominio-erro-cadastro">
          {criar.error?.message || "Não foi possível cadastrar o condomínio."}
        </p>
      )}

      {!value.casaDeRua && !value.condominio && (
        <p className="text-xs text-muted-foreground" data-testid="imovel-condominio-pendente">
          {legadoEmCondominio
            ? "Marcado como “em condomínio” no cadastro antigo: vincule o condomínio."
            : "Necessário para o contrato: vincule o condomínio ou marque “Casa de rua”."}
        </p>
      )}
    </div>
  );
}
