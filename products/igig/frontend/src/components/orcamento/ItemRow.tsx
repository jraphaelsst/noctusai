/**
 * One orçamento line. Recurring items pick weekdays (S T Q Q S S D) + a
 * quantity per day; one-off items take a monthly quantity. The monthly count
 * and subtotal shown are the SERVER's (`/calcular`); until that answer lands
 * the row shows its own estimate, marked as such.
 */
import { Minus, Plus, Trash2 } from "lucide-react";
import { Input, Switch } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";

import { WeekdayToggles } from "@/components/orcamento/WeekdayToggles";
import { brl } from "@/lib/format";
import { quantidadeMensalEstimada } from "@/lib/weekdays";
import type { OrcamentoItem, OrcamentoItemInput } from "@/types/crm";

export interface ItemRowProps {
  item: OrcamentoItemInput;
  /** The server's computed line, when the latest `/calcular` covers it. */
  calculado?: Pick<OrcamentoItem, "quantidade_mensal" | "subtotal"> | null;
  onChange: (patch: Partial<OrcamentoItemInput>) => void;
  onRemove: () => void;
  disabled?: boolean;
}

export function ItemRow({ item, calculado, onChange, onRemove, disabled }: ItemRowProps) {
  const qtdMensal = calculado?.quantidade_mensal ?? quantidadeMensalEstimada(item);
  const subtotal = calculado?.subtotal ?? item.preco_unitario * qtdMensal;
  const estimado = !calculado;
  const nome = item.descricao || "Item";

  return (
    <li className="rounded-lg border border-border bg-card p-3" data-testid="orcamento-item">
      <div className="flex items-start gap-2">
        <Input
          aria-label="Descrição do item"
          value={item.descricao}
          disabled={disabled}
          onChange={(e) => onChange({ descricao: e.target.value })}
          className="min-w-0 flex-1"
        />
        {!disabled ? (
          <button
            type="button"
            aria-label={`Remover ${nome}`}
            onClick={onRemove}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:items-end">
        <label className="block text-xs text-muted-foreground">
          Preço unitário
          <Input
            type="number"
            inputMode="decimal"
            min={0}
            step="0.01"
            aria-label={`Preço unitário — ${nome}`}
            value={Number.isFinite(item.preco_unitario) ? item.preco_unitario : 0}
            disabled={disabled}
            onChange={(e) => onChange({ preco_unitario: Math.max(0, Number(e.target.value) || 0) })}
            className="mt-1 sm:w-32"
          />
        </label>
        <label className="flex items-center gap-2 self-end pb-2 text-xs text-muted-foreground">
          <Switch
            aria-label={`Recorrente — ${nome}`}
            checked={item.recorrente}
            disabled={disabled}
            onCheckedChange={(v: boolean) => onChange({ recorrente: v })}
          />
          Recorrente
        </label>
      </div>

      {item.recorrente ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <WeekdayToggles
            value={item.dias_semana}
            onChange={(mask) => onChange({ dias_semana: mask })}
            disabled={disabled}
            label={nome}
          />
          <Stepper
            label={`Quantidade por dia — ${nome}`}
            sufixo="/dia"
            value={item.qtd_por_dia}
            min={1}
            disabled={disabled}
            onChange={(v) => onChange({ qtd_por_dia: v })}
          />
        </div>
      ) : (
        <div className="mt-3">
          <Stepper
            label={`Quantidade por mês — ${nome}`}
            sufixo="/mês"
            value={item.quantidade}
            min={1}
            disabled={disabled}
            onChange={(v) => onChange({ quantidade: v })}
          />
        </div>
      )}

      <p
        className={cn("mt-3 text-right text-xs tabular-nums", estimado ? "text-muted-foreground" : "text-foreground")}
        data-testid="item-resumo"
      >
        {estimado ? "≈ " : ""}
        {qtdMensal}/mês · <span className="font-medium">{brl(subtotal)}</span>
      </p>
    </li>
  );
}

function Stepper({
  label,
  sufixo,
  value,
  min,
  disabled,
  onChange,
}: {
  label: string;
  sufixo: string;
  value: number;
  min: number;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1" role="group" aria-label={label}>
      <button
        type="button"
        aria-label="Diminuir"
        disabled={disabled || value <= min}
        onClick={() => onChange(Math.max(min, value - 1))}
        className="flex h-10 w-10 items-center justify-center rounded-md border border-border disabled:opacity-40 sm:h-8 sm:w-8"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className="min-w-[3.5rem] text-center text-sm tabular-nums" aria-live="polite">
        {value}
        <span className="text-xs text-muted-foreground">{sufixo}</span>
      </span>
      <button
        type="button"
        aria-label="Aumentar"
        disabled={disabled}
        onClick={() => onChange(value + 1)}
        className="flex h-10 w-10 items-center justify-center rounded-md border border-border disabled:opacity-40 sm:h-8 sm:w-8"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
