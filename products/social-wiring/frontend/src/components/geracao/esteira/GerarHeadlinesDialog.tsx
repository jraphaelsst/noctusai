/**
 * "Gerar headlines" from the post card (esteira-contract.md §6.2 item 2).
 * Reuses the existing generation forms (`FormMePublico` / `FormViral`) with the
 * marca fixed and `post_id` sent, the existing `ProgressoLote`, and the existing
 * `HeadlinesGeradasModal` (with "Usar neste post"). Nothing here re-implements them.
 */
import { useState } from "react";

import { FormMePublico } from "@/components/geracao/headlines/FormMePublico";
import { FormViral } from "@/components/geracao/headlines/FormViral";
import { ProgressoLote } from "@/components/geracao/headlines/lote";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useLote } from "@/hooks/geracao/useHeadlines";
import { emAndamento } from "@/components/geracao/labels";
import type { HeadlineLote } from "@/types/geracao";

type Modo = "me" | "public" | "viral";
const ROTULO: Record<Modo, string> = { me: "Me", public: "Público", viral: "Viral" };

export interface GerarHeadlinesDialogProps {
  open: boolean;
  onClose: () => void;
  marcaId: string;
  postId: string;
  /** The batch reached a terminal state: the caller shows its headlines. */
  onConcluido: (loteId: string) => void;
}

export function GerarHeadlinesDialog({ open, onClose, marcaId, postId, onConcluido }: GerarHeadlinesDialogProps) {
  const [modo, setModo] = useState<Modo>("me");
  const [loteId, setLoteId] = useState<string | null>(null);
  const loteQ = useLote(open ? loteId : null);
  const lote: HeadlineLote | undefined = loteQ.data;
  const rodando = !!loteId && (!lote || emAndamento(lote.status));

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto" data-testid="gerar-headlines-dialog">
        <DialogHeader>
          <DialogTitle>Gerar headlines para este post</DialogTitle>
          <DialogDescription>As 10 headlines ficam na biblioteca; você escolhe qual usar neste post.</DialogDescription>
        </DialogHeader>
        {loteId && loteQ.isError && !lote ? (
          <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="gerar-headlines-erro">
            <p>Não foi possível acompanhar a geração.</p>
            <Button size="sm" variant="outline" onClick={() => loteQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : rodando ? (
          lote ? (
            <ProgressoLote lote={lote} />
          ) : (
            <div className="h-24 animate-pulse rounded bg-muted" data-testid="gerar-headlines-carregando" />
          )
        ) : lote ? (
          <div className="space-y-3 text-sm" data-testid="gerar-headlines-pronto">
            <p>{lote.status === "falha" ? "A geração falhou." : "Headlines geradas."}</p>
            <div className="flex gap-2">
              {lote.status !== "falha" && <Button onClick={() => onConcluido(lote.id)}>Ver headlines</Button>}
              <Button variant="outline" onClick={() => setLoteId(null)}>
                Gerar de novo
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-2">
              {(Object.keys(ROTULO) as Modo[]).map((m) => (
                <Button key={m} size="sm" variant={modo === m ? "default" : "outline"} onClick={() => setModo(m)}>
                  {ROTULO[m]}
                </Button>
              ))}
            </div>
            <section className="rounded-lg border p-4">
              {modo === "viral" ? (
                <FormViral marcaId={marcaId} postId={postId} onCriado={(l) => setLoteId(l.id)} />
              ) : (
                <FormMePublico key={modo} who={modo} marcaId={marcaId} postId={postId} onCriado={(l) => setLoteId(l.id)} />
              )}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
