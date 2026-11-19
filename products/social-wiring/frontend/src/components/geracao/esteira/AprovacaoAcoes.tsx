/**
 * Approve / reject controls for one approval target of a post: headline, roteiro or final media
 * (criacao-pipeline-contract.md §1/§7 S11). Approval is mandatory; "Reprovar" sends the item back to
 * refine and REQUIRES a reason (the seed `MotivoMoveDialog`). A refusal is never silent: the server's
 * pt-BR message goes to a toast and the buttons stay available to retry.
 */
import { useState } from "react";
import { MotivoMoveDialog } from "@noctusai/lib/components";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { mensagemAprovacao, useAprovarEtapa } from "@/hooks/geracao/useCriacao";
import type { AlvoAprovacao } from "@/types/esteira";

const ROTULO: Record<AlvoAprovacao, { aprovado: string; sucesso: string; devolvido: string; reprovar: string }> = {
  headline: {
    aprovado: "Headline aprovada",
    sucesso: "Headline aprovada.",
    devolvido: "Headline devolvida para refinamento.",
    reprovar: "Reprovar headline",
  },
  roteiro: {
    aprovado: "Roteiro aprovado",
    sucesso: "Roteiro aprovado.",
    devolvido: "Roteiro devolvido para refinamento.",
    reprovar: "Reprovar roteiro",
  },
  midia: {
    aprovado: "Mídia aprovada",
    sucesso: "Mídia aprovada.",
    devolvido: "Mídia devolvida para a criação.",
    reprovar: "Reprovar mídia",
  },
};

export interface AprovacaoAcoesProps {
  postId: string;
  alvo: AlvoAprovacao;
  /** Already approved (server-derived). */
  aprovado: boolean;
  /** There is something to decide on (e.g. the headline exists / the media is ready). */
  disponivel: boolean;
  /** Why the controls are disabled when `disponivel` is false (shown as text, not only a tooltip). */
  indisponivelMotivo?: string;
}

export function AprovacaoAcoes({ postId, alvo, aprovado, disponivel, indisponivelMotivo }: AprovacaoAcoesProps) {
  const [reprovando, setReprovando] = useState(false);
  const aprovar = useAprovarEtapa();
  const r = ROTULO[alvo];
  const ocupado = aprovar.isPending;

  function decidir(decisao: "aprovar" | "reprovar", motivo?: string) {
    aprovar.mutate(
      { postId, alvo, decisao, motivo },
      {
        onSuccess: () => {
          toast.success(decisao === "aprovar" ? r.sucesso : r.devolvido);
          setReprovando(false);
        },
        onError: (e) => toast.error(mensagemAprovacao(e)),
      },
    );
  }

  return (
    <div className="space-y-2" data-testid={`aprovacao-${alvo}`}>
      {aprovado && (
        <p className="flex items-center gap-1 text-sm font-medium text-success" role="status">
          <Check className="h-4 w-4" aria-hidden /> {r.aprovado}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {!aprovado && (
          <Button size="sm" disabled={!disponivel || ocupado} onClick={() => decidir("aprovar")}>
            <Check className="mr-1 h-4 w-4" aria-hidden />
            {ocupado ? "Salvando…" : "Aprovar"}
          </Button>
        )}
        <Button size="sm" variant="outline" disabled={!disponivel || ocupado} onClick={() => setReprovando(true)}>
          <X className="mr-1 h-4 w-4" aria-hidden />
          Reprovar
        </Button>
      </div>
      {!disponivel && indisponivelMotivo && <p className="text-xs text-muted-foreground">{indisponivelMotivo}</p>}
      {reprovando && (
        <MotivoMoveDialog
          open
          required
          title={r.reprovar}
          description="Conte o que precisa mudar. A IA refina a partir deste motivo e o item volta para sua aprovação."
          placeholder="O que precisa mudar?"
          confirmLabel="Devolver para refinar"
          onCancel={() => setReprovando(false)}
          onConfirm={(m) => decidir("reprovar", m)}
        />
      )}
    </div>
  );
}
