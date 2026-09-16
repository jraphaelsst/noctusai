/**
 * `<MatriculaPermutasSecao/>` — one `<MatriculaPermutaGrupo/>` per permuta
 * ativo of the deal, each with its own matrícula picker (migration 115).
 *
 * 🔴 WHY THIS IS A SEPARATE COMPONENT FROM `MatriculaAtosContainer`
 * -----------------------------------------------------------------
 * Two reasons, both mechanical:
 *
 * 1. `usePermutaAtivos()` fetches the org's whole ativo catalog, and the vast
 *    majority of deals have no permuta at all. Rendering this component only
 *    when the deal HAS ativos keeps that request off every other contract —
 *    which a hook called unconditionally in the parent could not do (rules of
 *    hooks).
 * 2. Each group needs its OWN `useMatriculaExtracoes` + `useMatriculaAtos`,
 *    and hooks cannot be called in a loop. One component instance per ativo
 *    is what makes per-group queries legal.
 *
 * The DRAFT still belongs to the parent: the PUT replaces the object's quote
 * and every permuta's in one body.
 */
import MatriculaPermutaGrupo from "@/components/card/MatriculaPermutaGrupo";
import { useMatriculaExtracoes } from "@/hooks/useMatriculas";
import { useMatriculaAtos } from "@/hooks/useMatriculaEstrutura";
import { usePermutaAtivos, type PermutaAtivo } from "@/hooks/usePermutas";

/** One group's draft — `extracaoId` null until a matrícula is picked. */
export interface PermutaDraft {
  extracaoId: string | null;
  atoIds: string[];
}

export interface MatriculaPermutasSecaoProps {
  /** The ativo ids this deal pays with — resolved to catalog rows here. */
  ativoIds: string[];
  drafts: Record<string, PermutaDraft>;
  onDraftChange: (permutaAtivoId: string, draft: PermutaDraft) => void;
  saving: boolean;
  errorMessage?: string | null;
  onSalvar: () => void;
}

/** What the operator needs to recognise the property, from whatever the ativo
 *  row actually carries — never a blank line. */
export function rotuloDoAtivo(ativo: PermutaAtivo): string {
  const partes = [
    ativo.imovel_codigo ?? ativo.codigo,
    ativo.tipo_imovel,
    [ativo.bairro, ativo.cidade].filter(Boolean).join(", ") || null,
  ].filter(Boolean);
  return partes.length > 0 ? partes.join(" · ") : "Ativo de permuta";
}

function Grupo({
  ativo,
  draft,
  onDraftChange,
  saving,
  errorMessage,
  onSalvar,
}: {
  ativo: PermutaAtivo;
  draft: PermutaDraft;
  onDraftChange: (permutaAtivoId: string, draft: PermutaDraft) => void;
  saving: boolean;
  errorMessage?: string | null;
  onSalvar: () => void;
}) {
  // Narrowed to the ativo's own imóvel: the backend refuses a matrícula that
  // belongs to a different one, so offering those would be offering a 400.
  const codigo = ativo.imovel_codigo ?? null;
  const extracoesQuery = useMatriculaExtracoes(codigo ? { codigo } : undefined);
  const atosQuery = useMatriculaAtos(draft.extracaoId);

  return (
    <MatriculaPermutaGrupo
      permutaAtivoId={ativo.id}
      rotulo={rotuloDoAtivo(ativo)}
      codigo={codigo}
      extracoes={(extracoesQuery.data ?? []).map((e) => ({
        id: e.id,
        nome_arquivo: e.nome_arquivo,
        status: e.status,
        created_at: e.created_at,
      }))}
      // Two signals off `data`, never `isLoading`.
      // KB § PATTERNS/frontend/lying-loading-state.md
      extracoesLoading={extracoesQuery.isPending && !extracoesQuery.data}
      extracoesError={extracoesQuery.isError && !extracoesQuery.data}
      extracaoSelecionadaId={draft.extracaoId}
      onSelecionarExtracao={(id) =>
        // A different matrícula has no comparable act ids, so switching
        // starts the selection empty rather than keeping a stale one.
        onDraftChange(ativo.id, { extracaoId: id, atoIds: [] })
      }
      atos={atosQuery.data?.atos ?? []}
      atosLoading={atosQuery.isPending && !atosQuery.data}
      atosError={atosQuery.isError && !atosQuery.data}
      atoIds={draft.atoIds}
      onAtoIdsChange={(atoIds) => onDraftChange(ativo.id, { ...draft, atoIds })}
      saving={saving}
      errorMessage={errorMessage}
      onSalvar={onSalvar}
    />
  );
}

export function MatriculaPermutasSecao({
  ativoIds,
  drafts,
  onDraftChange,
  saving,
  errorMessage,
  onSalvar,
}: MatriculaPermutasSecaoProps) {
  const ativosQuery = usePermutaAtivos();
  const ativos = (ativosQuery.data ?? []).filter((a) => ativoIds.includes(a.id));

  return (
    <div className="space-y-2 border-t pt-2" data-testid="matricula-permutas">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Imóveis dados em permuta ({ativoIds.length})
      </p>

      {ativosQuery.isPending && !ativosQuery.data && (
        <p className="text-xs text-muted-foreground">Carregando ativos de permuta...</p>
      )}
      {ativosQuery.isError && !ativosQuery.data && (
        <p className="text-xs text-destructive" data-testid="matricula-permutas-erro">
          Não foi possível carregar os ativos de permuta.
        </p>
      )}
      {/* An id the catalog no longer resolves is SAID, not dropped: the deal
          still points at it, and a silently missing section reads as "this
          deal has no permuta". */}
      {ativosQuery.data && ativos.length < ativoIds.length && (
        <p className="text-xs text-amber-700" data-testid="matricula-permutas-nao-resolvidos">
          {ativoIds.length - ativos.length} ativo(s) de permuta desta negociação não foram
          encontrados no catálogo.
        </p>
      )}

      {ativos.map((ativo) => (
        <Grupo
          key={ativo.id}
          ativo={ativo}
          draft={drafts[ativo.id] ?? { extracaoId: null, atoIds: [] }}
          onDraftChange={onDraftChange}
          saving={saving}
          errorMessage={errorMessage}
          onSalvar={onSalvar}
        />
      ))}
    </div>
  );
}
