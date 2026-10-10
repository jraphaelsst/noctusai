/**
 * Post card, "Roteiro" section (esteira-contract.md §6.2 item 3, FE-2).
 * Create (existing `RoteiroAvancadoModal` with `postId`), bind an existing one,
 * edit (existing `EditarRoteiroModal`) or unbind.
 */
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EditarRoteiroModal } from "@/components/geracao/roteiro/EditarRoteiroModal";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { StatusBadge } from "@/components/geracao/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useDesvincularRoteiro, useVincularRoteiro } from "@/hooks/geracao/useEsteira";
import { useRoteiro, useRoteiros } from "@/hooks/geracao/useRoteiros";
import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";

function Picker({
  open,
  marcaId,
  postId,
  onClose,
}: {
  open: boolean;
  marcaId: string;
  postId: string;
  onClose: () => void;
}) {
  const q = useRoteiros(open ? marcaId : null);
  const vincular = useVincularRoteiro();
  const itens = q.data?.items ?? [];

  function usar(roteiroId: string) {
    vincular.mutate(
      { postId, roteiroId },
      {
        onSuccess: () => {
          toast.success("Roteiro vinculado ao post.");
          onClose();
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível vincular o roteiro.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="roteiro-picker">
        <DialogHeader>
          <DialogTitle>Vincular roteiro existente</DialogTitle>
          <DialogDescription>Meus roteiros da marca.</DialogDescription>
        </DialogHeader>
        <div className="max-h-72 space-y-2 overflow-y-auto">
          {q.showSkeleton ? (
            <div className="h-20 animate-pulse rounded bg-muted" data-testid="roteiro-picker-loading" />
          ) : q.isError && !q.data ? (
            <p className="text-sm text-destructive" data-testid="roteiro-picker-erro">
              Não foi possível carregar os roteiros.
            </p>
          ) : itens.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="roteiro-picker-vazio">
              Nenhum roteiro para esta marca.
            </p>
          ) : (
            itens.map((r) => {
              const ocupado = !!r.post && r.post.id !== postId;
              return (
                <div key={r.id} className="flex items-start justify-between gap-2 rounded border p-2 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium">{r.nome}</p>
                    {ocupado && <p className="text-xs text-muted-foreground">No post: {r.post?.titulo}</p>}
                  </div>
                  <Button size="sm" disabled={ocupado || vincular.isPending} onClick={() => usar(r.id)}>
                    Vincular
                  </Button>
                </div>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function RoteiroSecao({ post }: { post: PostDetalhe }) {
  const [criando, setCriando] = useState(false);
  const [vinculando, setVinculando] = useState(false);
  const [editando, setEditando] = useState(false);
  const qc = useQueryClient();
  const desvincular = useDesvincularRoteiro();
  const r = post.roteiro;
  const detalhe = useRoteiro(r?.id ?? null);

  function desvincularRoteiro() {
    desvincular.mutate(post.id, {
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível desvincular o roteiro.")),
    });
  }

  async function copiar(conteudo: string) {
    try {
      await navigator.clipboard.writeText(conteudo);
      toast.success("Roteiro copiado.");
    } catch {
      toast.error("Não foi possível copiar o roteiro.");
    }
  }

  return (
    <section className="space-y-3" data-testid="secao-roteiro">
      <h3 className="text-sm font-semibold">Roteiro</h3>
      {r ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium" data-testid="roteiro-nome">
              {r.nome}
            </span>
            <StatusBadge status={r.status} />
            {detalhe.data?.etapa && <span className="text-xs text-muted-foreground">{detalhe.data.etapa}</span>}
          </div>
          {r.headline_diferente && (
            <p className="text-sm text-amber-600" data-testid="roteiro-headline-diferente">
              Este roteiro foi escrito para outra headline.
            </p>
          )}
          {detalhe.showSkeleton ? (
            <div className="h-16 animate-pulse rounded bg-muted" data-testid="roteiro-loading" />
          ) : detalhe.isError && !detalhe.data ? (
            <p className="text-sm text-destructive" data-testid="roteiro-erro">
              Não foi possível carregar o roteiro.
            </p>
          ) : detalhe.data?.conteudo ? (
            <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded border p-3 text-sm">
              {detalhe.data.conteudo}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">O conteúdo ainda não está pronto.</p>
          )}
          <div className="flex flex-wrap gap-2">
            {detalhe.data?.conteudo && (
              <Button size="sm" variant="outline" onClick={() => copiar(detalhe.data!.conteudo as string)}>
                Copiar roteiro
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setEditando(true)}>
              Editar
            </Button>
            <Button size="sm" variant="outline" disabled={desvincular.isPending} onClick={desvincularRoteiro}>
              Desvincular
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground" data-testid="roteiro-vazio">
            Este post ainda não tem roteiro.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setCriando(true)}>
              Criar roteiro
            </Button>
            <Button size="sm" variant="outline" onClick={() => setVinculando(true)}>
              Vincular roteiro existente
            </Button>
          </div>
        </div>
      )}
      <RoteiroAvancadoModal
        open={criando}
        onOpenChange={setCriando}
        marcaId={post.marca_id}
        postId={post.id}
        onCriado={() => {
          void qc.invalidateQueries({ queryKey: ESTEIRA_KEY });
          void qc.invalidateQueries({ queryKey: [ESTEIRA_PIPELINE_KEY] });
        }}
        headlineInicial={post.headline ? { id: post.headline.id, texto: post.headline.texto } : null}
      />
      <Picker open={vinculando} marcaId={post.marca_id} postId={post.id} onClose={() => setVinculando(false)} />
      {r && <EditarRoteiroModal open={editando} onOpenChange={setEditando} roteiroId={r.id} />}
    </section>
  );
}
