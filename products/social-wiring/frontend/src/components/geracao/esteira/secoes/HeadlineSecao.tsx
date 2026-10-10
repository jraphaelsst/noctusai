/**
 * Post card, "Headline" section (esteira-contract.md §6.2 item 2, FE-2).
 * Bind an existing library headline, type one, or unbind. Editing text reuses the
 * existing `EditarHeadlineModal`. States: batch running, bound, unbound, error.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { EditarHeadlineModal } from "@/components/geracao/headlines/EditarHeadlineModal";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useDesvincularHeadline, useVincularHeadline } from "@/hooks/geracao/useEsteira";
import { useHeadlinesLista, type ListaHeadlines } from "@/hooks/geracao/useHeadlines";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";

const TEXTO_MAX = 1000;

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
  const [lista, setLista] = useState<ListaHeadlines>("favoritas");
  const q = useHeadlinesLista(open ? marcaId : null, lista);
  const vincular = useVincularHeadline();
  const itens = q.data?.items ?? [];

  function usar(headlineId: string) {
    vincular.mutate(
      { postId, body: { headline_id: headlineId } },
      {
        onSuccess: () => {
          toast.success("Headline vinculada ao post.");
          onClose();
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível vincular a headline.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="headline-picker">
        <DialogHeader>
          <DialogTitle>Escolher da biblioteca</DialogTitle>
          <DialogDescription>Headlines da marca. As que já estão em outro post ficam indisponíveis.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
          {(["favoritas", "sugeridas"] as const).map((l) => (
            <Button key={l} size="sm" variant={lista === l ? "default" : "outline"} onClick={() => setLista(l)}>
              {l === "favoritas" ? "Favoritas" : "Sugeridas"}
            </Button>
          ))}
        </div>
        <div className="max-h-72 space-y-2 overflow-y-auto">
          {q.showSkeleton ? (
            <div className="h-20 animate-pulse rounded bg-muted" data-testid="headline-picker-loading" />
          ) : q.isError && !q.data ? (
            <p className="text-sm text-destructive" data-testid="headline-picker-erro">
              Não foi possível carregar as headlines.
            </p>
          ) : itens.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="headline-picker-vazio">
              Nenhuma headline nesta lista.
            </p>
          ) : (
            itens.map((h) => {
              const ocupada = !!h.post && h.post.id !== postId;
              return (
                <div key={h.id} className="flex items-start justify-between gap-2 rounded border p-2 text-sm">
                  <div className="min-w-0">
                    <p>{h.texto}</p>
                    {ocupada && <p className="text-xs text-muted-foreground">No post: {h.post?.titulo}</p>}
                  </div>
                  <Button size="sm" disabled={ocupada || vincular.isPending} onClick={() => usar(h.id)}>
                    Usar neste post
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

export function HeadlineSecao({ post }: { post: PostDetalhe }) {
  const [picker, setPicker] = useState(false);
  const [editando, setEditando] = useState(false);
  const [digitando, setDigitando] = useState(false);
  const [texto, setTexto] = useState("");
  const vincular = useVincularHeadline();
  const desvincular = useDesvincularHeadline();
  const h = post.headline;

  function salvarTexto() {
    const t = texto.trim();
    if (!t) return;
    vincular.mutate(
      { postId: post.id, body: { texto: t } },
      {
        onSuccess: () => {
          setDigitando(false);
          setTexto("");
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar a headline.")),
      },
    );
  }

  function desvincularHeadline() {
    desvincular.mutate(post.id, {
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível desvincular a headline.")),
    });
  }

  return (
    <section className="space-y-3" data-testid="secao-headline">
      <h3 className="text-sm font-semibold">Headline</h3>
      {post.lote_ativo && (
        <p className="text-sm text-muted-foreground" data-testid="headline-gerando">
          Gerando headlines{post.lote_ativo.etapa ? `: ${post.lote_ativo.etapa}` : ""}
        </p>
      )}
      {h ? (
        <div className="space-y-2">
          <p className="rounded border p-3 text-sm" data-testid="headline-texto">
            {h.favorita ? "♥ " : ""}
            {h.texto}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setEditando(true)}>
              Editar
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPicker(true)}>
              Trocar headline
            </Button>
            <Button size="sm" variant="outline" disabled={desvincular.isPending} onClick={desvincularHeadline}>
              Desvincular
            </Button>
            <Button size="sm" variant="link" asChild>
              <Link to={`/media-creation/headlines/favoritas?hid=${encodeURIComponent(h.id)}`}>
                Ver na biblioteca
              </Link>
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground" data-testid="headline-vazia">
            Este post ainda não tem headline.
          </p>
          {digitando ? (
            <div className="space-y-2">
              <Textarea
                aria-label="Texto da headline"
                maxLength={TEXTO_MAX}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
              />
              <div className="flex gap-2">
                <Button size="sm" disabled={!texto.trim() || vincular.isPending} onClick={salvarTexto}>
                  Salvar headline
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDigitando(false)}>
                  Cancelar
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setPicker(true)}>
                Escolher da biblioteca
              </Button>
              <Button size="sm" variant="outline" onClick={() => setDigitando(true)}>
                Escrever a minha
              </Button>
            </div>
          )}
        </div>
      )}
      <Picker open={picker} marcaId={post.marca_id} postId={post.id} onClose={() => setPicker(false)} />
      {h && (
        <EditarHeadlineModal
          open={editando}
          onOpenChange={setEditando}
          headline={{ id: h.id, texto: h.texto, texto_original: null }}
        />
      )}
    </section>
  );
}
