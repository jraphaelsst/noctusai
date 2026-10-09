import type { PesquisaVariable } from "@/hooks/usePesquisa";
import { cn } from "@/lib/utils";
import { agruparVariaveis } from "./labels";

interface Props {
  id?: string;
  value: string;
  onChange: (slug: string) => void;
  variaveis: PesquisaVariable[];
  /** Label of the empty option (value ""). */
  vazioRotulo: string;
  ariaLabel: string;
  className?: string;
}

/** Variable picker grouped by `grupo` (native select: accessible + testable). */
export function VariavelSelect({ id, value, onChange, variaveis, vazioRotulo, ariaLabel, className }: Props) {
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        className,
      )}
    >
      <option value="">{vazioRotulo}</option>
      {agruparVariaveis(variaveis).map((g) => (
        <optgroup key={g.grupo} label={g.rotulo}>
          {g.variaveis.map((v) => (
            <option key={v.slug} value={v.slug}>
              {v.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
