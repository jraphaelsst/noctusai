/**
 * `<MatriculaPermutaGrupo/>` — the acts quoted from ONE exchanged property's
 * matrícula (migration 115).
 *
 * 🔴 WHY THIS IS A SECTION PER ATIVO, NOT A SECOND MODE OF THE OBJECT PICKER
 * --------------------------------------------------------------------------
 * A deal paid partly in property describes EACH of those properties in the
 * contract, from that property's own matrícula. Its acts come from a
 * different extraction, its imóvel is a different `codigo`, and the backend
 * checks the pairing per group (`_exigir_permuta_compativel`). One picker
 * switched between them would make "which property am I quoting?" a mode you
 * have to remember instead of a section you can see.
 *
 * 🔴 THE TEXT IS LITERAL, TYPOS INCLUDED — same USER DECISION as the object
 * quote: acts are SELECTED, never edited. Every body renders `pre-wrap`.
 *
 * PRESENTATIONAL (S3 split): props in, callbacks out, zero queries. The draft
 * lives in `MatriculaAtosContainer`, because `PUT /contratos/{id}/atos`
 * replaces the object's quote AND every permuta's in one body — so one place
 * has to hold all of them.
 */
import { AlertCircle, ChevronDown, Loader2, Repeat } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

import type { MatriculaAto } from "@/hooks/useMatriculaEstrutura";
import type { MatriculaExtracaoOpcao } from "@/components/card/MatriculaAtosSelector";

export interface MatriculaPermutaGrupoProps {
  permutaAtivoId: string;
  /** How the operator recognises this property ("AP1234 · Apartamento, Centro"). */
  rotulo: string;
  /** The ativo's imóvel código, when it has one — the matrícula MUST be this
   *  property's, and the backend refuses anything else. */
  codigo: string | null;

  extracoes: MatriculaExtracaoOpcao[];
  extracoesLoading: boolean;
  extracoesError: boolean;

  extracaoSelecionadaId: string | null;
  onSelecionarExtracao: (id: string) => void;

  atos: MatriculaAto[];
  atosLoading: boolean;
  atosError: boolean;

  /** In CONTRACT order (click order). */
  atoIds: string[];
  onAtoIdsChange: (atoIds: string[]) => void;

  saving: boolean;
  /** The server's refusal for THIS group, verbatim. */
  errorMessage?: string | null;
  onSalvar: () => void;
}

function rotuloDoAto(ato: Pick<MatriculaAto, "kind" | "numero" | "rotulo">): string {
  if (ato.kind === "abertura") return "Abertura da matrícula";
  const numero = ato.numero != null ? `-${ato.numero}` : "";
  return `${ato.kind}${numero} · ${ato.rotulo || ato.kind}`;
}

export default function MatriculaPermutaGrupo({
  permutaAtivoId,
  rotulo,
  codigo,
  extracoes,
  extracoesLoading,
  extracoesError,
  extracaoSelecionadaId,
  onSelecionarExtracao,
  atos,
  atosLoading,
  atosError,
  atoIds,
  onAtoIdsChange,
  saving,
  errorMessage,
  onSalvar,
}: MatriculaPermutaGrupoProps) {
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const atosPorId = new Map(atos.map((a) => [a.id, a]));

  function alternarAto(atoId: string) {
    onAtoIdsChange(
      atoIds.includes(atoId) ? atoIds.filter((id) => id !== atoId) : [...atoIds, atoId],
    );
  }

  // Byte-for-byte, no separator — same join the server's `_citacao` does.
  const preview = atoIds.map((id) => atosPorId.get(id)?.texto ?? "").join("");

  return (
    <div
      className="space-y-2 rounded-md border border-dashed p-2.5"
      data-testid={`matricula-permuta-${permutaAtivoId}`}
    >
      <div className="flex items-center gap-1.5">
        <Repeat className="h-3.5 w-3.5 text-muted-foreground" />
        <p className="text-xs font-semibold">{rotulo}</p>
        {codigo && (
          <Badge variant="outline" className="text-[10px]">
            {codigo}
          </Badge>
        )}
      </div>

      {!codigo && (
        <p
          className="text-xs text-amber-700"
          data-testid={`matricula-permuta-sem-codigo-${permutaAtivoId}`}
        >
          Este ativo de permuta não está vinculado a um imóvel do catálogo — vincule-o
          para poder selecionar a matrícula dele.
        </p>
      )}

      {extracoesError && (
        <p
          className="text-xs text-destructive"
          data-testid={`matricula-permuta-extracoes-erro-${permutaAtivoId}`}
        >
          Não foi possível carregar as matrículas deste imóvel.
        </p>
      )}

      {extracoesLoading && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Carregando matrículas...
        </p>
      )}

      {!extracoesLoading && !extracoesError && extracoes.length === 0 && (
        <p
          className="text-xs text-muted-foreground"
          data-testid={`matricula-permuta-vazio-${permutaAtivoId}`}
        >
          Nenhuma matrícula transcrita para este imóvel.
        </p>
      )}

      {extracoes.length > 0 && (
        <ul className="max-h-24 divide-y overflow-y-auto rounded border text-xs">
          {extracoes.map((ext) => (
            <li key={ext.id}>
              <button
                type="button"
                onClick={() => onSelecionarExtracao(ext.id)}
                disabled={ext.status !== "concluida"}
                className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                data-testid={`matricula-permuta-extracao-${permutaAtivoId}-${ext.id}`}
              >
                <span className="truncate">{ext.nome_arquivo}</span>
                {extracaoSelecionadaId === ext.id && (
                  <Badge variant="secondary" className="shrink-0 text-[10px]">
                    selecionada
                  </Badge>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {extracaoSelecionadaId && (
        <>
          {atosLoading && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Carregando atos...
            </p>
          )}
          {atosError && (
            <p
              className="text-xs text-destructive"
              data-testid={`matricula-permuta-atos-erro-${permutaAtivoId}`}
            >
              Não foi possível carregar os atos desta matrícula.
            </p>
          )}
          {atos.length > 0 && (
            <ul
              className="max-h-40 space-y-1 overflow-y-auto"
              data-testid={`matricula-permuta-atos-${permutaAtivoId}`}
            >
              {atos.map((ato) => {
                const expandido = expandidos.has(ato.id);
                return (
                  <li key={ato.id} className="rounded border p-1.5">
                    <div className="flex items-start gap-2">
                      <Checkbox
                        checked={atoIds.includes(ato.id)}
                        onCheckedChange={() => alternarAto(ato.id)}
                        data-testid={`matricula-permuta-ato-checkbox-${permutaAtivoId}-${ato.id}`}
                      />
                      <div className="min-w-0 flex-1">
                        <Collapsible
                          open={expandido}
                          onOpenChange={() =>
                            setExpandidos((atual) => {
                              const copia = new Set(atual);
                              if (copia.has(ato.id)) copia.delete(ato.id);
                              else copia.add(ato.id);
                              return copia;
                            })
                          }
                        >
                          <CollapsibleTrigger asChild>
                            <button
                              type="button"
                              className="flex items-center gap-1 text-left text-[11px] font-medium"
                            >
                              <ChevronDown
                                className={`h-3 w-3 shrink-0 transition-transform ${expandido ? "rotate-180" : ""}`}
                              />
                              {rotuloDoAto(ato)}
                            </button>
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            <p className="mt-1 whitespace-pre-wrap rounded bg-muted/40 p-1.5 font-mono text-[11px] leading-relaxed">
                              {ato.texto}
                            </p>
                          </CollapsibleContent>
                        </Collapsible>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <p className="text-[11px] text-muted-foreground">
            {atoIds.length === 0
              ? "Nenhum ato selecionado para esta permuta."
              : `${atoIds.length} ato(s) na ordem do contrato.`}
          </p>

          {preview && (
            <p
              className="max-h-24 overflow-y-auto whitespace-pre-wrap rounded bg-muted/30 p-1.5 font-mono text-[11px] leading-relaxed"
              data-testid={`matricula-permuta-preview-${permutaAtivoId}`}
            >
              {preview}
            </p>
          )}
        </>
      )}

      {errorMessage && (
        <p
          className="flex items-start gap-1.5 text-xs text-destructive"
          data-testid={`matricula-permuta-erro-${permutaAtivoId}`}
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {errorMessage}
        </p>
      )}

      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-7 text-xs"
        disabled={saving || !extracaoSelecionadaId || atoIds.length === 0}
        onClick={onSalvar}
        data-testid={`matricula-permuta-salvar-${permutaAtivoId}`}
      >
        {saving && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
        Salvar seleção da permuta
      </Button>
    </div>
  );
}
