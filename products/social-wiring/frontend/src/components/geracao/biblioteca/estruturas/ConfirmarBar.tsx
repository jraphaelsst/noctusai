/** "N campos aguardam revisão" + Confirmar todos (admin only; renders nothing when nothing is pending). */
import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  pendentes: number;
  /** An unsaved draft: confirming would race the edit, so the button waits for Salvar / Descartar. */
  alteracoesNaoSalvas: boolean;
  pending: boolean;
  onConfirmarTodos: () => void;
}

export function ConfirmarBar({ pendentes, alteracoesNaoSalvas, pending, onConfirmarTodos }: Props) {
  if (pendentes <= 0) return null;
  return (
    <div
      role="status"
      data-testid="confirmar-bar"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm"
    >
      <p className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          {pendentes === 1 ? "1 campo aguarda" : `${pendentes} campos aguardam`} revisão. Eles já podem ser usados pelas
          organizações; confirmar apenas registra que alguém conferiu.
        </span>
      </p>
      <div className="flex items-center gap-2">
        {alteracoesNaoSalvas && (
          <span className="text-xs text-muted-foreground">Salve ou descarte as alterações para confirmar.</span>
        )}
        <Button size="sm" onClick={onConfirmarTodos} disabled={pending || alteracoesNaoSalvas}>
          {pending ? "Confirmando..." : "Confirmar todos"}
        </Button>
      </div>
    </div>
  );
}
