/**
 * `<ItensRevisaoLista/>` — the WORDING the final legal review must read
 * (contrato-partes-CONTRACT §5–6, migration 193): free-text obligations the
 * team typed (seller obligations, permuta delivery) and a company party's
 * wording. Shown verbatim, one block per item — there is nothing to confirm
 * per item; the review's approval covers them.
 *
 * Shared by the readiness section (`geracao.itens_revisao`, "the review will
 * read…") and the review itself (`revisao_juridica.itens`, "read before
 * approving") so both say the same thing about the same text.
 */
import { BookOpenCheck } from "lucide-react";

import type { ItemRevisaoJuridica } from "@/hooks/useContratos";

export function ItensRevisaoLista({
  itens,
  titulo,
  testId,
  tom = "neutro",
}: {
  itens: ItemRevisaoJuridica[] | undefined;
  titulo: string;
  testId: string;
  tom?: "neutro" | "revisao";
}) {
  if (!itens || itens.length === 0) return null;
  const borda = tom === "revisao" ? "border-amber-200 bg-white/70" : "border-muted bg-muted/30";
  return (
    <div className="space-y-1.5" data-testid={testId}>
      <p className="flex items-center gap-1.5 text-xs font-medium">
        <BookOpenCheck className="h-3.5 w-3.5 shrink-0" />
        {titulo}
      </p>
      <ul className="space-y-1.5">
        {itens.map((it, i) => (
          <li
            key={`${it.codigo}-${i}`}
            className={`rounded border px-2 py-1.5 text-xs ${borda}`}
            data-testid={`${testId}-item-${it.codigo}`}
          >
            <p className="font-medium">{it.titulo}</p>
            <p className="mt-0.5 whitespace-pre-line text-muted-foreground">{it.texto}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ItensRevisaoLista;
