/**
 * Stage select in the post card header (esteira-contract.md §6.2). A change goes
 * through `esteiraPipeline.useMoveCard` (`POST /posts/{id}/mover-etapa`) with the
 * SAME rules as the board: `decidirMovimento` picks the reason dialog (backward /
 * cancelado) or the permalink dialog (postado) before the request is sent.
 */
import { useState } from "react";
import { MotivoMoveDialog } from "@noctusai/lib/components";
import { toast } from "sonner";

import { mensagemErro } from "@/components/cerebro/labels";
import { esteiraPipeline } from "@/lib/pipelines";
import {
  decidirMovimento,
  ehPendencias,
  MENSAGEM_PENDENCIAS,
  type DecisaoMovimento,
} from "./moveRules";
import { PostadoDialog } from "./PostadoDialog";

type Motivo = Extract<DecisaoMovimento, { tipo: "motivo" }>;
type Pendente =
  | { tipo: "motivo"; regra: Motivo; paraId: string }
  | { tipo: "postado"; paraId: string };

export function EtapaSelect({ postId, etapaId }: { postId: string; etapaId: string }) {
  const stagesQ = esteiraPipeline.useStages();
  const mover = esteiraPipeline.useMoveCard({
    onError: (erro) =>
      toast.error(ehPendencias(erro) ? MENSAGEM_PENDENCIAS : mensagemErro(erro, "Não foi possível mover o post.")),
  });
  const [pendente, setPendente] = useState<Pendente | null>(null);

  const etapas = [...(stagesQ.data ?? [])].filter((s) => s.ativo || s.id === etapaId).sort((a, b) => a.posicao - b.posicao);
  const atual = etapas.find((s) => s.id === etapaId);

  function enviar(paraId: string, extra: { motivo?: string; extra?: Record<string, unknown> } = {}) {
    mover.mutate({ cardId: postId, toStageId: paraId, ...extra });
  }

  function escolher(paraId: string) {
    const para = etapas.find((s) => s.id === paraId);
    if (!para || !atual || para.id === atual.id) return;
    const direction = para.posicao > atual.posicao ? "forward" : para.posicao < atual.posicao ? "backward" : "same";
    const regra = decidirMovimento({ direction, fromStage: atual, toStage: para });
    if (regra.tipo === "seguir") enviar(paraId);
    else if (regra.tipo === "motivo") setPendente({ tipo: "motivo", regra, paraId });
    else setPendente({ tipo: "postado", paraId });
  }

  if (stagesQ.isPending && !stagesQ.data) {
    return <div className="h-8 w-32 animate-pulse rounded bg-muted" data-testid="etapa-loading" />;
  }
  if (stagesQ.isError && !stagesQ.data) {
    return (
      <span className="text-xs text-destructive" role="alert" data-testid="etapa-erro">
        Etapas indisponíveis
      </span>
    );
  }

  return (
    <>
      <select
        aria-label="Etapa"
        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
        value={etapaId}
        disabled={mover.isPending}
        onChange={(e) => escolher(e.target.value)}
      >
        {!atual && <option value={etapaId}>Etapa removida</option>}
        {etapas.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>
      {pendente?.tipo === "motivo" && (
        <MotivoMoveDialog
          open
          required
          title={pendente.regra.titulo}
          description={pendente.regra.descricao}
          placeholder={pendente.regra.placeholder}
          confirmLabel={pendente.regra.confirmar}
          onCancel={() => setPendente(null)}
          onConfirm={(motivo) => {
            enviar(pendente.paraId, { motivo });
            setPendente(null);
          }}
        />
      )}
      {pendente?.tipo === "postado" && (
        <PostadoDialog
          open
          onCancel={() => setPendente(null)}
          onConfirm={(permalink) => {
            enviar(pendente.paraId, permalink ? { extra: { permalink } } : {});
            setPendente(null);
          }}
        />
      )}
    </>
  );
}
