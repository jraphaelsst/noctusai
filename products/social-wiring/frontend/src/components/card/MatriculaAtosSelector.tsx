/**
 * `<MatriculaAtosSelector/>` — the contract's "Descrição do imóvel
 * (matrícula)" section: pick which matrícula acts a contract quotes, in
 * order.
 *
 * 🔴 USER DECISION: THE TEXT IS LITERAL, TYPOS INCLUDED
 * -------------------------------------------------------
 * The property description quoted into a contract is the matrícula's own
 * text, verbatim — the operator SELECTS acts, never edits their wording.
 * Every act body here renders with `white-space: pre-wrap` and is never
 * trimmed or autocorrected; the live preview is the plain concatenation of
 * the chosen acts' literal `texto`, matching `obter_selecao`'s own join
 * (no separator — the segmenter's spans already carry their line breaks).
 *
 * PRESENTATIONAL (S3, `lead-card-hub-p2-PROJECT.md` ruling): props in,
 * callbacks out, zero `useQuery`/`useMutation` calls in this file. The
 * container that fetches (`MatriculaAtosContainer`, in `components/`, NOT
 * `components/card/`) owns `useMatriculaExtracoes` / `useMatriculaAtos` /
 * `useContratoAtos` / `useDefinirContratoAtos` and hands this component
 * already-resolved data — same split `ImovelCartorioCard` and
 * `PessoaDocumentosPanel` use between an authoring card and its container.
 *
 * NOT a canonical organ (`noc-organ-consume-check`, run first): `@noctusai/lib`
 * ships no ordered-multi-select-with-literal-text-preview shape. Reorder is
 * UP/DOWN buttons rather than `CriarRoteiroDialog`'s dnd-kit drag: that
 * dialog composes a casual visiting ITINERARY; this orders sentences that
 * will be quoted into a legal document, where a precise, keyboard-reachable,
 * directly-testable control reads better than a pointer gesture jsdom cannot
 * exercise either way (see that file's own test-file note on the same point).
 */
import { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Link2,
  Loader2,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";

import type {
  ContratoAtoSelecionado,
  MatriculaActor,
  MatriculaAto,
} from "@/hooks/useMatriculaEstrutura";

export interface MatriculaExtracaoOpcao {
  id: string;
  nome_arquivo: string;
  status: "pendente" | "processando" | "concluida" | "erro";
  created_at: string;
}

export interface MatriculaAtosSelectorProps {
  contratoId: string;
  /** The imóvel código, when known — informs the picker's placeholder only;
   *  every extraction is still offered regardless of it. */
  codigo?: string | null;

  extracoes: MatriculaExtracaoOpcao[];
  extracoesLoading: boolean;
  extracoesError: boolean;
  buscaExtracao: string;
  onBuscaExtracaoChange: (v: string) => void;

  /** The extraction currently being browsed for acts — `null` until the
   *  operator picks one (or it defaults to the persisted selection's). */
  extracaoSelecionadaId: string | null;
  onSelecionarExtracao: (id: string) => void;

  /**
   * Bug H — existing transcriptions with NO `codigo` at all (predate this
   * imóvel's registry identity, or uploaded standalone) — the scoped search
   * above can never surface them, since they have nothing to match `codigo`
   * against. A secondary section, offered ALONGSIDE the scoped results (not
   * only when they come up empty) — an operator may not know yet that the
   * matrícula they want is sitting unlinked. Empty array when `codigo` is
   * unknown (nothing to link TO).
   */
  extracoesSemImovel?: MatriculaExtracaoOpcao[];
  extracoesSemImovelLoading?: boolean;
  /** Links one unlinked extraction to THIS imóvel, then selects it — the
   *  container's job (it owns the mutation + `codigo`). */
  onVincularExtracao?: (extracaoId: string) => void;
  vinculando?: boolean;

  atos: MatriculaAto[];
  atosLoading: boolean;
  atosError: boolean;

  /** The contract's PERSISTED selection, or `undefined` while loading. */
  selecao: ContratoAtoSelecionado[] | undefined;
  selecaoExtracaoId: string | null;
  selecaoLoading: boolean;
  selecaoError: boolean;
  selecionadoPor: MatriculaActor | null;
  selecionadoEm: string | null;

  saving: boolean;
  onSave: (input: { extracaoId: string; atoIds: string[] }) => void;

  /**
   * OPTIONALLY CONTROLLED. Omit both and this component owns its draft (the
   * original behaviour, still used by every existing caller). Pass them and
   * the PARENT owns it — which is what the permuta flow needs: `PUT
   * /contratos/{id}/atos` replaces the object's quote AND every permuta's in
   * one body, so whoever composes that body has to know both drafts.
   */
  draftAtoIds?: string[];
  onDraftAtoIdsChange?: (atoIds: string[]) => void;
  /** The server's refusal, verbatim — it names the imóvel mismatch. */
  errorMessage?: string | null;
}

const KIND_LABEL: Record<MatriculaAto["kind"], string> = {
  abertura: "Abertura",
  R: "Registro",
  AV: "Averbação",
};

function rotuloDoAto(ato: Pick<MatriculaAto, "kind" | "numero" | "rotulo">): string {
  if (ato.kind === "abertura") return "Abertura da matrícula";
  const numero = ato.numero != null ? `-${ato.numero}` : "";
  return `${ato.kind}${numero} · ${ato.rotulo || KIND_LABEL[ato.kind]}`;
}

/** Byte-for-byte concatenation, same as the server's `obter_selecao` —
 *  no separator, because each act's slice already carries its own line
 *  breaks. */
function previewTexto(atoIds: string[], porId: Map<string, MatriculaAto>): string {
  return atoIds.map((id) => porId.get(id)?.texto ?? "").join("");
}

export default function MatriculaAtosSelector({
  contratoId,
  codigo,
  extracoes,
  extracoesLoading,
  extracoesError,
  buscaExtracao,
  onBuscaExtracaoChange,
  extracaoSelecionadaId,
  onSelecionarExtracao,
  extracoesSemImovel = [],
  extracoesSemImovelLoading = false,
  onVincularExtracao,
  vinculando = false,
  atos,
  atosLoading,
  atosError,
  selecao,
  selecaoExtracaoId,
  selecaoLoading,
  selecaoError,
  selecionadoPor,
  selecionadoEm,
  saving,
  onSave,
  draftAtoIds: draftAtoIdsProp,
  onDraftAtoIdsChange,
  errorMessage,
}: MatriculaAtosSelectorProps) {
  // Controlled-or-not, decided by whether the prop was PASSED — not by
  // whether it is empty: `[]` is a real draft (nothing selected), so
  // `draftAtoIdsProp || draftInterno` would silently hand control back to
  // this component the moment the parent cleared the selection.
  const [draftInterno, setDraftInterno] = useState<string[]>([]);
  const controlado = draftAtoIdsProp !== undefined;
  const draftAtoIds = controlado ? draftAtoIdsProp : draftInterno;
  const setDraftAtoIds = (next: string[] | ((atual: string[]) => string[])) => {
    const valor = typeof next === "function" ? next(draftAtoIds) : next;
    if (controlado) onDraftAtoIdsChange?.(valor);
    else setDraftInterno(valor);
  };
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());

  // Re-seed the draft from the PERSISTED selection whenever it changes AND
  // it belongs to the extraction currently being browsed — acts from a
  // different extraction have no comparable ids, so browsing a different
  // matrícula starts the draft empty rather than showing a stale selection.
  // Keyed on the ids themselves (not object identity), same discipline
  // `ImovelCartorioCard.toDraft` uses, so an unrelated refetch does not stomp
  // an edit in progress.
  const persistedIds = (selecao ?? []).map((a) => a.ato_id).join(",");
  useEffect(() => {
    // In controlled mode the parent seeds (and re-seeds) the draft — doing it
    // here too would fight it on every refetch.
    if (controlado) return;
    if (extracaoSelecionadaId && extracaoSelecionadaId === selecaoExtracaoId) {
      setDraftAtoIds(persistedIds ? persistedIds.split(",") : []);
    } else {
      setDraftAtoIds([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extracaoSelecionadaId, selecaoExtracaoId, persistedIds]);

  const atosPorId = new Map(atos.map((a) => [a.id, a]));
  const resultadosBusca = buscaExtracao.trim()
    ? extracoes.filter((e) =>
        e.nome_arquivo.toLowerCase().includes(buscaExtracao.trim().toLowerCase()),
      )
    : extracoes;

  function alternarAto(atoId: string) {
    setDraftAtoIds((atual) =>
      atual.includes(atoId) ? atual.filter((id) => id !== atoId) : [...atual, atoId],
    );
  }

  function moverAto(index: number, direcao: -1 | 1) {
    setDraftAtoIds((atual) => {
      const destino = index + direcao;
      if (destino < 0 || destino >= atual.length) return atual;
      const copia = [...atual];
      [copia[index], copia[destino]] = [copia[destino], copia[index]];
      return copia;
    });
  }

  function alternarExpandido(atoId: string) {
    setExpandidos((atual) => {
      const copia = new Set(atual);
      if (copia.has(atoId)) copia.delete(atoId);
      else copia.add(atoId);
      return copia;
    });
  }

  function salvar() {
    if (!extracaoSelecionadaId) return;
    onSave({ extracaoId: extracaoSelecionadaId, atoIds: draftAtoIds });
  }

  const preview = previewTexto(draftAtoIds, atosPorId);

  return (
    <div className="space-y-3 rounded-md border p-3" data-testid={`matricula-atos-${contratoId}`}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Descrição do imóvel (matrícula)</h4>
        {selecionadoPor && (
          <p className="text-[11px] text-muted-foreground">
            Selecionado por {selecionadoPor.nome ?? "—"}
            {selecionadoEm ? ` em ${new Date(selecionadoEm).toLocaleString("pt-BR")}` : ""}
          </p>
        )}
      </div>

      {selecaoError && (
        <p className="text-xs text-destructive" data-testid="matricula-atos-selecao-erro">
          Não foi possível carregar a seleção atual.
        </p>
      )}

      {/* ─── Extraction picker ────────────────────────────────────────── */}
      <div className="space-y-1.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={buscaExtracao}
            onChange={(e) => onBuscaExtracaoChange(e.target.value)}
            placeholder={codigo ? `Buscar matrícula de ${codigo}...` : "Buscar matrícula transcrita..."}
            className="h-8 pl-8 text-sm"
            data-testid="matricula-atos-busca"
          />
          {extracoesLoading && (
            <Loader2 className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-muted-foreground" />
          )}
        </div>

        {extracoesError && (
          <p className="text-xs text-destructive" data-testid="matricula-atos-extracoes-erro">
            Não foi possível carregar as matrículas transcritas.
          </p>
        )}

        {!extracoesError && resultadosBusca.length === 0 && !extracoesLoading && (
          <p className="text-xs text-muted-foreground">Nenhuma matrícula transcrita encontrada.</p>
        )}

        {resultadosBusca.length > 0 && (
          <ul className="max-h-32 divide-y overflow-y-auto rounded-md border text-sm">
            {resultadosBusca.map((ext) => (
              <li key={ext.id}>
                <button
                  type="button"
                  onClick={() => onSelecionarExtracao(ext.id)}
                  disabled={ext.status !== "concluida"}
                  className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid={`matricula-atos-extracao-${ext.id}`}
                >
                  <span className="truncate">{ext.nome_arquivo}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {ext.status !== "concluida" && (
                      <span className="text-[10px] text-muted-foreground">
                        {ext.status === "erro" ? "erro na extração" : "processando"}
                      </span>
                    )}
                    {extracaoSelecionadaId === ext.id && (
                      <Badge variant="secondary" className="text-[10px]">
                        selecionada
                      </Badge>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ─── Matrículas sem imóvel vinculado (Bug H) ────────────────────
          Offered alongside the scoped search, not only when it comes up
          empty — the operator does not need to already know a matrícula
          is unlinked to find it here. Absent entirely when the container
          has no `codigo` to link TO (nothing shows). */}
      {(extracoesSemImovel.length > 0 || extracoesSemImovelLoading) && (
        <div className="space-y-1.5 border-t pt-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Matrículas sem imóvel vinculado
          </p>
          {extracoesSemImovelLoading && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando...
            </p>
          )}
          {!extracoesSemImovelLoading && extracoesSemImovel.length > 0 && (
            <ul
              className="max-h-32 divide-y overflow-y-auto rounded-md border text-sm"
              data-testid="matricula-atos-sem-imovel"
            >
              {extracoesSemImovel.map((ext) => (
                <li
                  key={ext.id}
                  className="flex items-center justify-between gap-2 px-2.5 py-1.5"
                >
                  <span className="min-w-0 flex-1 truncate">{ext.nome_arquivo}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-6 shrink-0 gap-1 px-2 text-[11px]"
                    disabled={vinculando || !onVincularExtracao}
                    onClick={() => onVincularExtracao?.(ext.id)}
                    data-testid={`matricula-atos-vincular-${ext.id}`}
                  >
                    {vinculando ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Link2 className="h-3 w-3" />
                    )}
                    Vincular
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!extracaoSelecionadaId && (
        <p className="text-xs text-muted-foreground" data-testid="matricula-atos-vazio">
          Selecione uma matrícula transcrita para escolher os atos.
        </p>
      )}

      {extracaoSelecionadaId && (
        <>
          {/* ─── Acts catalog ─────────────────────────────────────────── */}
          {atosLoading && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando atos...
            </p>
          )}
          {atosError && (
            <p className="text-xs text-destructive" data-testid="matricula-atos-erro">
              Não foi possível carregar os atos desta matrícula.
            </p>
          )}
          {!atosLoading && !atosError && atos.length === 0 && (
            <p className="text-xs text-muted-foreground">
              Esta matrícula ainda não tem atos segmentados.
            </p>
          )}
          {!atosLoading && atos.length > 0 && (
            <ul className="max-h-56 space-y-1 overflow-y-auto" data-testid="matricula-atos-catalogo">
              {atos.map((ato) => {
                const marcado = draftAtoIds.includes(ato.id);
                const expandido = expandidos.has(ato.id);
                return (
                  <li key={ato.id} className="rounded border p-2" data-testid={`matricula-ato-${ato.id}`}>
                    <div className="flex items-start gap-2">
                      <Checkbox
                        checked={marcado}
                        onCheckedChange={() => alternarAto(ato.id)}
                        data-testid={`matricula-ato-checkbox-${ato.id}`}
                      />
                      <div className="min-w-0 flex-1">
                        <Collapsible open={expandido} onOpenChange={() => alternarExpandido(ato.id)}>
                          <CollapsibleTrigger asChild>
                            <button
                              type="button"
                              className="flex items-center gap-1 text-left text-xs font-medium"
                              data-testid={`matricula-ato-toggle-${ato.id}`}
                            >
                              <ChevronDown
                                className={`h-3 w-3 shrink-0 transition-transform ${expandido ? "rotate-180" : ""}`}
                              />
                              {rotuloDoAto(ato)}
                            </button>
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            <p
                              className="mt-1.5 whitespace-pre-wrap rounded bg-muted/40 p-2 font-mono text-xs leading-relaxed"
                              data-testid={`matricula-ato-texto-${ato.id}`}
                            >
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

          {/* ─── Selected, in contract order ──────────────────────────── */}
          <div className="space-y-1.5 border-t pt-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ordem no contrato ({draftAtoIds.length})
            </p>
            {draftAtoIds.length === 0 ? (
              <p className="text-xs text-muted-foreground" data-testid="matricula-atos-selecao-vazia">
                Nenhum ato selecionado ainda.
              </p>
            ) : (
              <ul className="space-y-1" data-testid="matricula-atos-selecionados">
                {draftAtoIds.map((id, index) => {
                  const ato = atosPorId.get(id);
                  return (
                    <li
                      key={id}
                      className="flex items-center justify-between gap-2 rounded border border-dashed p-1.5 text-xs"
                      data-testid={`matricula-ato-selecionado-${id}`}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        <span className="mr-1.5 rounded bg-muted px-1 py-0.5 font-semibold tabular-nums">
                          {index + 1}
                        </span>
                        {ato ? rotuloDoAto(ato) : id}
                      </span>
                      <span className="flex shrink-0 items-center gap-0.5">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6"
                          disabled={index === 0}
                          onClick={() => moverAto(index, -1)}
                          aria-label="Mover para cima"
                          data-testid={`matricula-ato-subir-${id}`}
                        >
                          <ArrowUp className="h-3 w-3" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6"
                          disabled={index === draftAtoIds.length - 1}
                          onClick={() => moverAto(index, 1)}
                          aria-label="Mover para baixo"
                          data-testid={`matricula-ato-descer-${id}`}
                        >
                          <ArrowDown className="h-3 w-3" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6"
                          onClick={() => alternarAto(id)}
                          aria-label="Remover da seleção"
                          data-testid={`matricula-ato-remover-${id}`}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* ─── Live preview — the LITERAL, unedited concatenation ───── */}
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Prévia
            </p>
            {preview ? (
              <p
                className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-muted/30 p-2 font-mono text-xs leading-relaxed"
                data-testid="matricula-atos-preview"
              >
                {preview}
              </p>
            ) : (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <AlertCircle className="h-3.5 w-3.5" /> Nada selecionado ainda.
              </p>
            )}
          </div>

          {errorMessage && (
            // Verbatim: the 400 names WHICH rule refused (a matrícula from
            // another imóvel, an extraction not linked to one, a transcription
            // still running). A generic "erro ao salvar" would hide the only
            // part the operator can act on.
            <p className="text-xs text-destructive" data-testid="matricula-atos-erro-salvar">
              {errorMessage}
            </p>
          )}

          <Button
            type="button"
            size="sm"
            onClick={salvar}
            disabled={saving || selecaoLoading}
            data-testid="matricula-atos-salvar"
          >
            {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Salvar seleção
          </Button>
        </>
      )}
    </div>
  );
}
