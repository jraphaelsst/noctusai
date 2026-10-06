/**
 * `<ClausulasExtrasEditor/>` — "Condições especiais por cláusula" (migration
 * 207). Signed contracts carry deal-specific text no card field holds (an extra
 * objeto paragraph, a financing paragraph in preço, a rewritten
 * irretratabilidade, an extra vistoria sentence). One collapsible row per
 * clause the contract generator knows (`termos_opcoes.clausulas`, derived
 * server-side from its own registry — never a list kept here), each with a
 * textarea and a "substituir a cláusula padrão" switch.
 *
 * Controlled and presentational: the parent (`TermosNegocioSection`) owns the
 * draft and submits it through the termos mutation with everything else (the
 * PUT replaces the whole object). A clause with no text sends nothing —
 * "no special conditions" is the absence of an entry.
 */
import { ChevronDown } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { ClausulaExtraModo, TermosOpcoes } from "@/types/negociacaoEstruturada";

export interface ClausulaExtraDraft {
  texto: string;
  modo: ClausulaExtraModo;
}

export type ClausulasExtrasDraft = Record<string, ClausulaExtraDraft>;

interface Props {
  clausulas: TermosOpcoes["clausulas"];
  value: ClausulasExtrasDraft;
  onChange: (chave: string, next: ClausulaExtraDraft) => void;
}

const VAZIO: ClausulaExtraDraft = { texto: "", modo: "acrescentar" };

export default function ClausulasExtrasEditor({ clausulas, value, onChange }: Props) {
  return (
    <section className="space-y-3" data-testid="termos-clausulas-extras">
      <div className="space-y-1">
        <h4 className="text-sm font-medium">Condições especiais por cláusula</h4>
        <p className="text-xs text-muted-foreground">
          Texto próprio deste negócio, impresso como digitado (um parágrafo por linha) na cláusula
          indicada. Todo texto digitado aqui vira item da revisão jurídica.
        </p>
      </div>
      <div className="space-y-2">
        {clausulas.map((c) => {
          const atual = value[c.chave] ?? VAZIO;
          const preenchida = atual.texto.trim() !== "";
          const substitui = preenchida && atual.modo === "substituir";
          return (
            <Collapsible
              key={c.chave}
              defaultOpen={preenchida}
              className="rounded-md border"
              data-testid={`clausula-extra-${c.chave}`}
            >
              <CollapsibleTrigger
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium"
                data-testid={`clausula-extra-${c.chave}-toggle`}
              >
                <span>{c.rotulo}</span>
                <span className="flex items-center gap-2">
                  {substitui && (
                    <span
                      className="rounded-md bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive"
                      data-testid={`clausula-extra-${c.chave}-badge`}
                    >
                      Substitui a padrão
                    </span>
                  )}
                  {preenchida && !substitui && (
                    <span
                      className="rounded-md bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground"
                      data-testid={`clausula-extra-${c.chave}-badge`}
                    >
                      Com texto
                    </span>
                  )}
                  <ChevronDown className="h-4 w-4 shrink-0" />
                </span>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 border-t px-3 py-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`clausula-extra-${c.chave}-texto`}>
                    Texto para &ldquo;{c.rotulo}&rdquo;
                  </Label>
                  <Textarea
                    id={`clausula-extra-${c.chave}-texto`}
                    data-testid={`clausula-extra-${c.chave}-texto`}
                    value={atual.texto}
                    onChange={(e) => onChange(c.chave, { ...atual, texto: e.target.value })}
                  />
                  {c.condicional && (
                    <p className="text-xs text-muted-foreground">
                      Esta cláusula só existe em alguns contratos; se o contrato deste negócio não a
                      tiver, a geração avisa e o texto não é impresso.
                    </p>
                  )}
                </div>
                <div className="flex items-start gap-2">
                  <Switch
                    id={`clausula-extra-${c.chave}-substituir`}
                    data-testid={`clausula-extra-${c.chave}-substituir`}
                    checked={atual.modo === "substituir"}
                    onCheckedChange={(v) =>
                      onChange(c.chave, { ...atual, modo: v ? "substituir" : "acrescentar" })
                    }
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor={`clausula-extra-${c.chave}-substituir`}>
                      Substituir a cláusula padrão
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {atual.modo === "substituir"
                        ? "O texto padrão desta cláusula não será impresso: vale só o que for digitado (a 1ª linha é o corpo da cláusula; as demais viram parágrafos). Título e numeração são mantidos."
                        : "Desligado, o texto digitado é acrescentado depois dos parágrafos padrão, numerado em sequência."}
                    </p>
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          );
        })}
      </div>
    </section>
  );
}
