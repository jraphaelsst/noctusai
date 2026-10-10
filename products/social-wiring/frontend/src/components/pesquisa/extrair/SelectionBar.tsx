import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

interface SelectionBarProps {
  selecionados: number;
  max: number;
  reextrair: boolean;
  onReextrair: (v: boolean) => void;
  onSelecionarRecentes: () => void;
  onLimpar: () => void;
  onExtrair: () => void;
  submitting: boolean;
  /** Reason the submit is blocked (shown as text), or null when allowed. */
  bloqueio: string | null;
}

export function SelectionBar({
  selecionados,
  max,
  reextrair,
  onReextrair,
  onSelecionarRecentes,
  onLimpar,
  onExtrair,
  submitting,
  bloqueio,
}: SelectionBarProps) {
  return (
    <div className="sticky bottom-0 z-10 flex flex-col gap-2 rounded-lg border bg-background p-3 shadow-md">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span>
          {selecionados} de {max} selecionado{selecionados === 1 ? "" : "s"}
        </span>
        <Button type="button" variant="link" size="sm" onClick={onSelecionarRecentes}>
          Selecionar os {max} mais recentes
        </Button>
        <Button type="button" variant="link" size="sm" onClick={onLimpar} disabled={selecionados === 0}>
          Limpar
        </Button>
        <label className="flex items-center gap-2">
          <Checkbox checked={reextrair} onCheckedChange={(v) => onReextrair(v === true)} />
          Reextrair posts já extraídos
        </label>
        <Button
          type="button"
          className="ml-auto"
          onClick={onExtrair}
          disabled={selecionados === 0 || submitting || !!bloqueio}
        >
          Extrair ({selecionados})
        </Button>
      </div>
      {bloqueio && <p className="text-xs text-destructive">{bloqueio}</p>}
    </div>
  );
}
