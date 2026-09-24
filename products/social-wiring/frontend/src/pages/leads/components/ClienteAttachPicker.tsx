/**
 * ClienteAttachPicker — pick ONE already-registered cliente, live, by nome
 * OR celular OR email (`GET /api/clientes?q=`), with a "+" escape hatch to
 * register a new person inline without leaving the page.
 *
 * Mirrors `ImovelCodigoPicker`'s idiom (debounced typeahead + a "+"
 * escape-hatch affordance next to it) — NOT a canonical `@noctusai/lib`
 * organ. That picker's own header already establishes why this shape stays
 * per-product (`noc-organ-consume-check` run first, same verdict here):
 * `@noctusai/lib` ships `MultiSelectPopover`, a fixed-option multi-select
 * over a list it already holds, not a single-value debounced live-fetch
 * typeahead over an unbounded, server-searched set.
 *
 * 🔴 "Registering" a new cliente via the "+" dialog does NOT call a
 * create-cliente endpoint — none exists in this product. Every `clientes`
 * row is derived FROM a lead's `cliente_nome` + `contato` by
 * `clientes_service.attach_lead_now` (synchronous, on every `POST
 * /api/leads`) / `run_backfill` (the scheduled sweep) — never inserted
 * directly by a client request (`leads.id → atendimentos.cliente_id` is a
 * RESOLVED fact, not a foreign key `leads` itself carries; the `leads`
 * table has no `cliente_id` column at all — §5.3 of
 * `leads-module-PROJECT.md` is frozen on that shape). So the "+" dialog
 * collects nome+contato locally and hands back a DRAFT selection; the real
 * `clientes` row is created the same way every hand-typed lead's always has
 * been — by the outer "Novo lead" form's own submit.
 *
 * Picking an EXISTING cliente instead sends that cliente's own
 * `chave_canonica` (already E.164-phone/lowercased-email normalized) as the
 * new lead's `contato`, so `attach_lead_now`'s exact-key lookup
 * (`_find_existing_for_key`, keyed on `cliente_touches.chave_canonica`)
 * reattaches the new lead's card to that SAME person instead of creating a
 * duplicate — no `cliente_id` column needed for that guarantee to hold.
 */
import { useState } from "react";
import { Check, Loader2, Plus, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useClientesBusca, type Cliente } from "@/hooks/useClientes";
import { formatPhone } from "@noctusai/lib/phone";
import { NovoClienteInlineDialog } from "./NovoClienteInlineDialog";

/**
 * What the outer "Novo lead" form actually needs to submit — a cliente
 * picked from the DB (`isNovo: false`, real `clientes.id`) or one just
 * typed into the "+" dialog (`isNovo: true`, a client-side-only draft id).
 * Either way it reduces to `cliente_nome` + `contato` on submit — see the
 * module header for why no third shape (a real synchronous create) exists.
 */
export interface ClienteSelecionado {
  id: string;
  nome: string;
  contato: string | null;
  isNovo: boolean;
}

/** `formatPhone` for a phone, the bare lowercased address for an email —
 *  mirrors `leadDetailSections.contatoValue`'s branching, applied to a
 *  `Cliente` row instead of a `Lead`. */
function rotuloContato(c: Cliente): string | null {
  if (c.celular) return formatPhone(c.celular);
  if (c.email) return c.email.toLowerCase();
  if (c.chave_tipo === "email") return c.chave_canonica;
  return c.chave_canonica ? formatPhone(c.chave_canonica) : null;
}

/** The exact value sent as the new lead's `contato` when this cliente is
 *  chosen — `chave_canonica` first (see module header: it is what
 *  `attach_lead_now` matches on), falling back to the raw columns for a
 *  keyless cliente (`identidade_incerta`, no canonical key to reuse). */
function contatoParaAnexar(c: Cliente): string | null {
  return c.chave_canonica ?? c.celular ?? c.email ?? null;
}

export interface ClienteAttachPickerProps {
  value: ClienteSelecionado | null;
  onChange: (cliente: ClienteSelecionado | null) => void;
  disabled?: boolean;
  id?: string;
  "data-testid"?: string;
}

export function ClienteAttachPicker({
  value,
  onChange,
  disabled,
  id,
  "data-testid": testId = "cliente-attach-picker",
}: ClienteAttachPickerProps) {
  const [termo, setTermo] = useState("");
  const [novoAberto, setNovoAberto] = useState(false);
  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useClientesBusca(termoDebounced);

  // 🔴 `isPending || isFetching`, never `isLoading`: v5's `isLoading` is
  // false during a background refetch, so a "nenhum cliente" branch keyed
  // off it would render "sem resultados" over results that exist.
  const buscando = busca.isPending || busca.isFetching;
  const termoUtil = termoDebounced.trim().length >= 2;
  const resultados = busca.data?.items ?? [];
  const buscaVazia = termoUtil && !buscando && resultados.length === 0;

  function escolher(cliente: Cliente) {
    onChange({
      id: cliente.id,
      nome: cliente.nome,
      contato: contatoParaAnexar(cliente),
      isNovo: false,
    });
    setTermo("");
  }

  if (value) {
    return (
      <div
        className="flex items-center gap-2 rounded-md border px-3 py-2"
        data-testid={`${testId}-escolhido`}
      >
        <Check className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{value.nome}</p>
          {(value.contato || value.isNovo) && (
            <p className="truncate text-xs text-muted-foreground">
              {value.isNovo ? "Novo cliente" : value.contato}
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={disabled}
          onClick={() => onChange(null)}
          aria-label="Remover cliente selecionado"
          data-testid={`${testId}-limpar`}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5" data-testid={testId}>
      <div className="flex items-center gap-1.5">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            id={id}
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            placeholder="Nome, celular ou e-mail..."
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
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={disabled}
          onClick={() => setNovoAberto(true)}
          aria-label="Cadastrar novo cliente"
          data-testid={`${testId}-novo-abrir`}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {!termoUtil ? (
        <p className="text-xs text-muted-foreground">Digite ao menos 2 caracteres.</p>
      ) : buscaVazia ? (
        <p className="text-xs text-muted-foreground" data-testid={`${testId}-vazio`}>
          Nenhum cliente encontrado para "{termoDebounced.trim()}". Use o "+" para cadastrar.
        </p>
      ) : (
        <ul
          className="max-h-56 divide-y overflow-y-auto rounded-md border"
          data-testid={`${testId}-resultados`}
        >
          {resultados.map((cliente) => (
            <li key={cliente.id}>
              <button
                type="button"
                className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-muted"
                disabled={disabled}
                onClick={() => escolher(cliente)}
                data-testid={`${testId}-opcao-${cliente.id}`}
              >
                <span className="min-w-0 truncate font-medium">{cliente.nome}</span>
                {rotuloContato(cliente) && (
                  <span className="text-xs text-muted-foreground">{rotuloContato(cliente)}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      <NovoClienteInlineDialog
        open={novoAberto}
        onOpenChange={setNovoAberto}
        onCriado={(draft) => {
          onChange(draft);
          setNovoAberto(false);
          setTermo("");
        }}
        data-testid={`${testId}-novo`}
      />
    </div>
  );
}
