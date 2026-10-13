/**
 * `<FavorecidoCombobox/>` — searchable select over the org's ACTIVE favorecido
 * registry, with a "Novo favorecido" shortcut. Replaces free-typing payee
 * data on the card: you pick a registry entry, you don't retype bank data.
 *
 * The registry is org-small, so the search filters the loaded (masked) list
 * on the client — the typed term never leaves the browser, which also keeps a
 * CPF typed into the box out of any URL. Rows show the MASKED document only.
 *
 * Presentational over `useFavorecidos`; the dialog for "Novo favorecido" is
 * owned by the caller (`onNovo`) so the card can select the created record.
 */
import { useMemo, useState } from "react";
import { Check, ChevronsUpDown, Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useFavorecidos } from "@/hooks/useFavorecidosRegistro";
import { cn } from "@/lib/utils";

export interface FavorecidoComboboxProps {
  /** Selected registry id (controlled). */
  value: string | null;
  onChange: (favorecidoId: string) => void;
  /** "Novo favorecido" shortcut — the caller opens the create dialog. */
  onNovo: () => void;
  disabled?: boolean;
  id?: string;
}

function normalizar(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function FavorecidoCombobox({
  value,
  onChange,
  onNovo,
  disabled,
  id,
}: FavorecidoComboboxProps) {
  const query = useFavorecidos({ ativo: "ativos" });
  const [open, setOpen] = useState(false);
  const [busca, setBusca] = useState("");

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const items = query.data?.items ?? [];

  const filtrados = useMemo(() => {
    const termo = normalizar(busca.trim());
    if (!termo) return items;
    return items.filter((f) => normalizar(f.nome).includes(termo));
  }, [items, busca]);

  const selecionado = items.find((f) => f.id === value) ?? null;

  function escolher(favorecidoId: string) {
    onChange(favorecidoId);
    setOpen(false);
    setBusca("");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between font-normal"
          data-testid="favorecido-combobox"
        >
          <span className={cn("truncate", !selecionado && "text-muted-foreground")}>
            {selecionado ? selecionado.nome : "Selecionar favorecido do cadastro…"}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[var(--radix-popover-trigger-width)] min-w-72 space-y-2 p-2"
        data-testid="favorecido-combobox-lista"
      >
        <Input
          autoFocus
          value={busca}
          placeholder="Buscar por nome…"
          aria-label="Buscar favorecido por nome"
          onChange={(e) => setBusca(e.target.value)}
          data-testid="favorecido-combobox-busca"
        />
        <div className="max-h-56 space-y-0.5 overflow-y-auto" role="listbox">
          {showSkeleton ? (
            <p
              className="flex items-center gap-2 p-2 text-sm text-muted-foreground"
              data-testid="favorecido-combobox-skeleton"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando cadastro…
            </p>
          ) : query.isError && !query.data ? (
            <div className="space-y-2 p-2" data-testid="favorecido-combobox-erro">
              <p className="text-sm text-destructive">
                Não foi possível carregar os favorecidos.
              </p>
              <Button size="sm" variant="outline" onClick={() => query.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : filtrados.length === 0 ? (
            <p
              className="p-2 text-sm text-muted-foreground"
              data-testid="favorecido-combobox-vazio"
            >
              {items.length === 0
                ? "Nenhum favorecido cadastrado."
                : "Nenhum favorecido encontrado."}
            </p>
          ) : (
            filtrados.map((f) => (
              <button
                key={f.id}
                type="button"
                role="option"
                aria-selected={f.id === value}
                onClick={() => escolher(f.id)}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                data-testid={`favorecido-opcao-${f.id}`}
              >
                <Check
                  className={cn(
                    "h-4 w-4 shrink-0",
                    f.id === value ? "opacity-100" : "opacity-0",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{f.nome}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {[f.cpf_cnpj_mascarado, f.banco].filter(Boolean).join(" · ") || "—"}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
        {isRefreshing && (
          <p
            className="px-2 text-xs text-muted-foreground"
            data-testid="favorecido-combobox-refreshing"
          >
            Atualizando…
          </p>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          onClick={() => {
            setOpen(false);
            onNovo();
          }}
          data-testid="favorecido-combobox-novo"
        >
          <Plus className="mr-1 h-4 w-4" />
          Novo favorecido
        </Button>
      </PopoverContent>
    </Popover>
  );
}
