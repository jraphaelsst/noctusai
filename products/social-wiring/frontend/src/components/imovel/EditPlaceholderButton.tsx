/**
 * EditPlaceholderButton — the "editar" icon that does not edit anything.
 *
 * CONTRACT § 4: Vista rejects every write route on this key
 * (`/imoveis/alterar` / `/imoveis/cadastrar` / `/imoveis/excluir` all 404).
 * There is no editor to open. A button that silently no-ops on click IS a
 * silent error — so this one fires a toast that says exactly why nothing
 * happened, which is what makes the placeholder honest instead of a bug.
 *
 * Wraps the EXISTING `TooltipIconButton` (canonical-organ-consumption rule)
 * — no fork, no re-implementation. `label` drives both the tooltip and the
 * `aria-label` there.
 */
import { Pencil } from "lucide-react";
import { toast } from "sonner";

import { TooltipIconButton } from "@/components/card/TooltipIconButton";

const MENSAGEM =
  "Edição via plataforma ainda não disponível — o Vista não expõe rota de escrita. Chega quando migrarmos para o sistema próprio.";

export default function EditPlaceholderButton({
  label,
  testId,
}: {
  label: string;
  testId?: string;
}) {
  return (
    <TooltipIconButton
      label={label}
      icon={Pencil}
      testId={testId}
      onClick={() => toast.info(MENSAGEM)}
    />
  );
}
