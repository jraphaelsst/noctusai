/**
 * Banner de uma conversa cujo lead pediu para não ser mais contatado (ou cujo atendimento foi reativado): quando,
 * por quê e quem registrou. Texto simples — o registro completo e a reativação ficam no social-wiring (a tela de
 * opt-outs é da organização, não do agents). Nada é renderizado sem evento.
 */
import { BellOff, BellRing } from "lucide-react";
import type { OptOutEvento } from "@/api/studio/types-julia";
import { optOutData, optOutMotivo, optOutQuem } from "@/lib/optOut";

export function OptOutBanner({ evento }: { evento: OptOutEvento | null | undefined }) {
  if (!evento) return null;
  const reativado = evento.tipo === "reativacao";
  const Icone = reativado ? BellRing : BellOff;
  return (
    <div
      role="status"
      className={
        reativado
          ? "flex items-start gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-sm"
          : "flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm"
      }
      data-testid="optout-banner"
    >
      <Icone className={`mt-0.5 h-4 w-4 flex-shrink-0 ${reativado ? "text-primary" : "text-destructive"}`} />
      <p className="min-w-0 flex-1">
        {reativado ? "Atendimento reativado em" : "O lead pediu para não ser mais contatado em"} {optOutData(evento.em)} —{" "}
        {optOutMotivo(evento)}.{" "}
        <span className="text-muted-foreground">Registrado por: {optOutQuem(evento)}.</span>
      </p>
    </div>
  );
}
