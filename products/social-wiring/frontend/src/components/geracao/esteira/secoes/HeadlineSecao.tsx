/**
 * Post card, "Headline" section (esteira-contract.md §6.2 item 2, FE-2).
 * Bind an existing library headline, type one, or unbind. Editing text reuses the
 * existing `EditarHeadlineModal`. States: batch running, bound, unbound, error.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { GerarHeadlinesDialog } from "@/components/geracao/esteira/GerarHeadlinesDialog";
import { EditarHeadlineModal } from "@/components/geracao/headlines/EditarHeadlineModal";
import { HeadlinesGeradasModal } from "@/components/geracao/headlines/HeadlinesGeradasModal";
import { StatusBadge } from "@/components/geracao/StatusBadge";
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
import { useHeadline, useHeadlinesLista, useLotesDoPost, type ListaHeadlines } from "@/hooks/geracao/useHeadlines";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";

const TEXTO_MAX = 1000;

function Picker({
  open,
  marcaId,
  postId,
  onClose,
  onVerLote,
}: {
  open: boolean;
  marcaId: string;
  postId: string;
  onClose: () => void;
  onVerLote: (loteId: string) => void;
}) {
  const [lista, setLista] = useState<ListaHeadlines | "recentes">("favoritas");
  const q = useHeadlinesLista(open && lista !== "recentes" ? marcaId : null, lista === "recentes" ? "favoritas" : lista);
  const lotesQ = useLotesDoPost(open && lista === "recentes" ? marcaId : null, postId);
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
          {(["favoritas", "sugeridas", "recentes"] as const).map((l) => (
            <Button key={l} size="sm" variant={lista === l ? "default" : "outline"} onClick={() => setLista(l)}>
              {l === "favoritas" ? "Favoritas" : l === "sugeridas" ? "Sugeridas" : "Geradas recentemente"}
            </Button>
          ))}
        </div>
        <div className="max-h-72 space-y-2 overflow-y-auto">
          {lista === "recentes" ? (
            lotesQ.showSkeleton ? (
              <div className="h-20 animate-pulse rounded bg-muted" data-testid="headline-picker-loading" />
            ) : lotesQ.isError && !lotesQ.data ? (
              <p className="text-sm text-destructive" data-testid="headline-picker-erro">
                Não foi possível carregar os lotes deste post.
              </p>
            ) : (lotesQ.data?.items ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="headline-picker-vazio">
                Nenhum lote gerado para este post ainda.
              </p>
            ) : (
              (lotesQ.data?.items ?? []).map((l) => (
                <div key={l.id} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate">{l.resumo || "Lote de headlines"}</p>
                    <StatusBadge status={l.status} />
                  </div>
                  <Button size="sm" onClick={() => onVerLote(l.id)}>
                    Ver headlines
                  </Button>
                </div>
              ))
            )
          ) : q.showSkeleton ? (
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
  const [gerando, setGerando] = useState(false);
  const [loteVer, setLoteVer] = useState<string | null>(null);
  const vincular = useVincularHeadline();
  const desvincular = useDesvincularHeadline();
  const h = post.headline;
  // `ResumoHeadline` carries no `texto_original`; read the real row while editing so the
  // modal shows (and never loses) the AI original.
  const completa = useHeadline(editando && h ? h.id : null);

  // Stable identity: the modal resets its textarea whenever `headline` changes.
  const paraEditar = useMemo(
    () => (h ? { id: h.id, texto: h.texto, texto_original: completa.data?.texto_original ?? h.texto } : null),
    [h?.id, h?.texto, completa.data?.texto_original], // eslint-disable-line react-hooks/exhaustive-deps
  );

  function usarNoPost(headlineId: string) {
    vincular.mutate(
      { postId: post.id, body: { headline_id: headlineId } },
      {
        onSuccess: () => {
          toast.success("Headline vinculada ao post.");
          setLoteVer(null);
          setGerando(false);
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível vincular a headline.")),
      },
    );
  }

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
              <Button size="sm" variant="outline" onClick={() => setGerando(true)} disabled={!!post.lote_ativo}>
                Gerar headlines
              </Button>
              <Button size="sm" variant="outline" onClick={() => setDigitando(true)}>
                Escrever a minha
              </Button>
            </div>
          )}
        </div>
      )}
      <Picker
        open={picker}
        marcaId={post.marca_id}
        postId={post.id}
        onClose={() => setPicker(false)}
        onVerLote={(id) => {
          setPicker(false);
          setLoteVer(id);
        }}
      />
      <GerarHeadlinesDialog
        open={gerando}
        onClose={() => setGerando(false)}
        marcaId={post.marca_id}
        postId={post.id}
        onConcluido={(id) => {
          setGerando(false);
          setLoteVer(id);
        }}
      />
      <HeadlinesGeradasModal
        open={!!loteVer}
        onOpenChange={(o) => !o && setLoteVer(null)}
        loteId={loteVer}
        marcaId={post.marca_id}
        onUsarNoPost={(headline) => usarNoPost(headline.id)}
      />
      {paraEditar && (
        // Never `texto_original: null`: the modal would hide the AI original. Use the real row's
        // value (the PATCH sends only `texto`, so the stored original is never overwritten).
        <EditarHeadlineModal open={editando} onOpenChange={setEditando} headline={paraEditar} />
      )}
    </section>
  );
}
