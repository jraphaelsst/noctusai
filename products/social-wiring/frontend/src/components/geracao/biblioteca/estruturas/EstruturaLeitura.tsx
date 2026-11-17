/**
 * Read-only view of an Estrutura — what an org member sees (no provenance, no admin controls, no drafts:
 * the server strips them, and nothing here renders them). Also the view a platform admin gets while the
 * admin flag is still unknown.
 */
import { Badge } from "@/components/ui/badge";
import type { EstruturaDetalhe, TipoBloco } from "@/types/estruturas";
import { placeholdersDaFormula, resumoBloco } from "./rotulos";

export function EstruturaLeitura({ detalhe, tipos }: { detalhe: EstruturaDetalhe; tipos: TipoBloco[] }) {
  const placeholders = placeholdersDaFormula(detalhe.formula_headline);
  return (
    <div className="flex flex-col gap-5" data-testid="estrutura-leitura">
      <section aria-label="Fórmula da headline" className="flex flex-col gap-2 rounded-lg border p-4">
        <h2 className="text-lg font-semibold">Fórmula da headline</h2>
        <p className="whitespace-pre-wrap text-base">{detalhe.formula_headline}</p>
        {placeholders.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Os trechos entre colchetes são preenchidos com o Cérebro e a bio da sua organização.
          </p>
        )}
      </section>

      <section aria-label="Blocos" className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Blocos ({detalhe.blocos.length})</h2>
        {detalhe.blocos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Esta estrutura ainda não tem blocos.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {detalhe.blocos.map((b, i) => {
              const padrao = tipos.find((t) => t.id === b.tipo.id)?.instrucao_referencia;
              return (
                <li key={b.id} className="rounded-lg border bg-card p-3" data-testid={`bloco-leitura-${i + 1}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold">
                      {i + 1}. {b.nome}
                    </span>
                    <Badge variant="secondary">{b.tipo.nome}</Badge>
                    {resumoBloco(b) && <span className="text-xs text-muted-foreground">{resumoBloco(b)}</span>}
                  </div>
                  {(b.instrucao ?? padrao) && (
                    <p className="mt-2 whitespace-pre-wrap text-sm">{b.instrucao ?? padrao}</p>
                  )}
                  {b.nota && <p className="mt-2 text-xs italic text-muted-foreground">{b.nota}</p>}
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}
