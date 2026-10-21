/**
 * Banner de uma conversa cujo lead pediu para não ser mais contatado: quando, por quê, quem registrou e um
 * link para o registro completo (página Opt-outs). Nada é renderizado sem evento.
 */
import { Link } from "react-router-dom";
import { BellOff } from "lucide-react";
import type { OptOutEvento } from "@/api/studio/types-julia";
import { optOutData, optOutLink, optOutMotivo, optOutQuem } from "@/lib/optOut";

export function OptOutBanner({ evento }: { evento: OptOutEvento | null | undefined }) {
  if (!evento) return null;
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm"
      data-testid="optout-banner"
    >
      <BellOff className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
      <p className="min-w-0 flex-1">
        O lead pediu para não ser mais contatado em {optOutData(evento.em)} — {optOutMotivo(evento)}.{" "}
        <span className="text-muted-foreground">Registrado por: {optOutQuem(evento)}.</span>{" "}
        <Link to={optOutLink(evento.id)} className="font-medium text-primary underline" data-testid="optout-banner-link">
          Ver registro
        </Link>
      </p>
    </div>
  );
}
