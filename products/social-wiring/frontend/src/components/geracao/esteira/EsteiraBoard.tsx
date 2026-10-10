/**
 * `<EsteiraBoard filtros onOpenPost/>` — the Esteira de Reels kanban on the seed
 * `PipelineBoard` (esteira-contract.md §6.1; UX reference: igig's EsteiraBoard).
 *
 * - Data: `useEsteiraBoard` (the contract payload is `{colunas, orfaos}`, which
 *   `esteiraPipeline.useBoard` cannot unwrap). It is handed to `PipelineBoard`
 *   through a `hooks` override so the organ renders exactly what we fetched;
 *   moves and stage CRUD still come from `esteiraPipeline`.
 * - Moves: forward is free; backward / into cancelado ask a reason
 *   (`MotivoMoveDialog`); into postado asks the optional permalink.
 * - Loading: `showSkeleton = isPending && !data` for the first load only;
 *   a refetch keeps the board mounted and only shows a small indicator.
 * - Card click → `onOpenPost(id)` (the post dialog is FE-2's).
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  MotivoMoveDialog,
  PipelineBoard,
  type MoveDecision,
  type MoveIntentContext,
} from "@noctusai/lib/components";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { mensagemErro } from "@/components/cerebro/labels";
import { useEsteiraBoard, type EsteiraFiltros } from "@/hooks/geracao/useEsteira";
import { esteiraPipeline } from "@/lib/pipelines";
import type { PostCard } from "@/types/esteira";
import {
  decidirMovimento,
  ehPendencias,
  ESTEIRA_ROLE_LABELS,
  MENSAGEM_PENDENCIAS,
  type DecisaoMovimento,
} from "./moveRules";
import { PostadoDialog } from "./PostadoDialog";
import { PostCardFace } from "./PostCardFace";

export interface EsteiraBoardProps {
  filtros: EsteiraFiltros;
  /** Opens the post card dialog (FE-2). */
  onOpenPost: (id: string) => void;
  className?: string;
}

/** Seed default column, sized for a phone first (the board scrolls inside its own container). */
const COLUNA =
  "flex-shrink-0 w-[82vw] max-w-80 sm:w-80 rounded-lg border bg-card text-card-foreground shadow-sm " +
  "flex flex-col overflow-hidden max-h-[calc(100dvh-14rem)] " +
  "[&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto";

type Motivo = Extract<DecisaoMovimento, { tipo: "motivo" }>;
interface Pendente {
  resolve: (d: MoveDecision) => void;
}

export function EsteiraBoard({ filtros, onOpenPost, className }: EsteiraBoardProps) {
  const podeEditarEtapas = useIsOrgAdmin();
  const board = useEsteiraBoard(filtros);
  const [motivo, setMotivo] = useState<(Pendente & { regra: Motivo }) | null>(null);
  const [postado, setPostado] = useState<Pendente | null>(null);

  // Render exactly the query we own: `PipelineBoard` reads `hooks.useBoard`.
  const hooks = useMemo(
    () => ({
      ...esteiraPipeline,
      useBoard: (f?: Record<string, any>) => useEsteiraBoard(f ?? {}) as unknown as ReturnType<
        typeof esteiraPipeline.useBoard
      >,
    }),
    [],
  );

  const papelPorEtapa = useMemo(() => {
    const m = new Map<string, string | null>();
    for (const c of board.colunas ?? []) m.set(c.etapa, (c.stage as { papel?: string | null })?.papel ?? null);
    return m;
  }, [board.colunas]);

  function onBeforeMove(ctx: MoveIntentContext<PostCard>): MoveDecision | Promise<MoveDecision> {
    const regra = decidirMovimento(ctx);
    if (regra.tipo === "seguir") return true;
    if (regra.tipo === "motivo") {
      return new Promise<MoveDecision>((resolve) => setMotivo({ resolve, regra }));
    }
    return new Promise<MoveDecision>((resolve) => setPostado({ resolve }));
  }

  function fecharMotivo(d: MoveDecision) {
    motivo?.resolve(d);
    setMotivo(null);
  }

  if (board.showSkeleton) {
    return (
      <div className="flex gap-3 overflow-hidden" data-testid="esteira-skeleton">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-64 w-72 flex-shrink-0" />
        ))}
      </div>
    );
  }

  if (board.isError && !board.data) {
    return (
      <div className="rounded-md border border-destructive/40 p-6 text-sm" role="alert" data-testid="esteira-erro">
        <p className="mb-3 text-destructive">
          {mensagemErro(board.error, "Não foi possível carregar a esteira.")}
        </p>
        <Button size="sm" variant="outline" onClick={() => board.refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  }

  const total = (board.colunas ?? []).reduce((n, c) => n + c.total, 0);

  return (
    <div className={`min-w-0 max-w-full space-y-3 ${className ?? ""}`} data-testid="esteira-board">
      {/* `orfaos` is a bare int in the board payload (esteira-contract.md §5.1 #2:
          `{colunas:[...], orfaos:int}`), no items — so a count banner, not a list. */}
      {board.orfaos > 0 && (
        <div
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          data-testid="esteira-orfaos"
        >
          {board.orfaos === 1
            ? "1 post está em uma etapa removida ou inativa e não aparece no quadro."
            : `${board.orfaos} posts estão em etapas removidas ou inativas e não aparecem no quadro.`}{" "}
          Reative a etapa para vê-los novamente.
        </div>
      )}
      {board.isRefreshing && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="esteira-atualizando">
          <Loader2 className="h-3 w-3 animate-spin" />
          Atualizando…
        </div>
      )}
      {total === 0 && (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground" data-testid="esteira-vazio">
          Nenhum post ainda. Crie o primeiro ou transforme uma headline favorita em post.
        </p>
      )}

      <PipelineBoard
        hooks={hooks}
        filtros={filtros}
        className="min-w-0 max-w-full"
        columnClassName={COLUNA}
        renderCard={(post, { isDragging }) => (
          <PostCardFace
            post={post}
            papelEtapa={papelPorEtapa.get(post.etapa_id) ?? null}
            esconderMarca={Boolean(filtros.marca_id)}
            isDragging={isDragging}
            onClick={() => onOpenPost(post.id)}
          />
        )}
        onCardClick={(post) => onOpenPost(post.id)}
        showValue={false}
        emptyColumnLabel="Nenhum post"
        editableHeaders
        reorderableColumns
        canEditStages={podeEditarEtapas}
        roleLabels={ESTEIRA_ROLE_LABELS}
        onBeforeMove={onBeforeMove}
        onMoveError={(erro, vars) => {
          if (ehPendencias(erro)) {
            toast.error(MENSAGEM_PENDENCIAS, {
              action: { label: "Abrir post", onClick: () => onOpenPost(vars.cardId) },
            });
            return;
          }
          toast.error(mensagemErro(erro, "Não foi possível mover o post."));
        }}
      />

      {motivo && (
        <MotivoMoveDialog
          open
          required
          title={motivo.regra.titulo}
          description={motivo.regra.descricao}
          placeholder={motivo.regra.placeholder}
          confirmLabel={motivo.regra.confirmar}
          onCancel={() => fecharMotivo(false)}
          onConfirm={(m) => fecharMotivo({ motivo: m })}
        />
      )}
      {postado && (
        <PostadoDialog
          open
          onCancel={() => {
            postado.resolve(false);
            setPostado(null);
          }}
          onConfirm={(permalink) => {
            postado.resolve(permalink ? { extra: { permalink } } : true);
            setPostado(null);
          }}
        />
      )}
    </div>
  );
}

export default EsteiraBoard;
