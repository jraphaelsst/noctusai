/**
 * Post card, "Publicação" section (esteira-contract.md §6.2 item 5, FE-2).
 * Legenda, hashtags, primeiro comentário and permalink. "Gerar legenda com IA"
 * only FILLS the fields (the endpoint saves nothing); the user edits and presses
 * "Salvar" (`PATCH /posts/{id}`).
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAtualizarPost, useGerarLegenda } from "@/hooks/geracao/useEsteira";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";
import { permalinkValido } from "../moveRules";

export const LEGENDA_MAX = 2200;
export const HASHTAGS_MAX = 30;

/** "#a #b, c" -> ["a","b","c"]: leading `#` stripped, blanks and repeats dropped. */
export function parseHashtags(texto: string): string[] {
  const out: string[] = [];
  for (const bruto of texto.split(/[\s,]+/)) {
    const t = bruto.replace(/^#+/, "").trim();
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}
const formatHashtags = (h: string[]) => h.map((t) => `#${t}`).join(" ");

export function PublicacaoSecao({ post }: { post: PostDetalhe }) {
  const [legenda, setLegenda] = useState(post.legenda ?? "");
  const [hashtags, setHashtags] = useState(formatHashtags(post.hashtags));
  const [comentario, setComentario] = useState(post.primeiro_comentario ?? "");
  const [permalink, setPermalink] = useState(post.permalink ?? "");
  const [erroGerar, setErroGerar] = useState<string | null>(null);
  const gerar = useGerarLegenda();
  const atualizar = useAtualizarPost();

  const roteiroCompleto = post.roteiro?.status === "completo";
  const postado = !!post.postado_em;
  const tags = parseHashtags(hashtags);
  const excedeu = legenda.length > LEGENDA_MAX || tags.length > HASHTAGS_MAX;
  const permalinkOk = permalinkValido(permalink);

  function gerarLegenda() {
    setErroGerar(null);
    gerar.mutate(post.id, {
      onSuccess: (r) => {
        setLegenda(r.legenda);
        setHashtags(formatHashtags(r.hashtags));
        setComentario(r.primeiro_comentario);
        toast.success("Legenda gerada. Revise e salve.");
      },
      onError: (e) => {
        const msg = mensagemErroServidor(e, "Não foi possível gerar a legenda.");
        setErroGerar(msg);
        toast.error(msg);
      },
    });
  }

  function salvar() {
    atualizar.mutate(
      {
        id: post.id,
        patch: {
          legenda: legenda.trim() || null,
          hashtags: tags,
          primeiro_comentario: comentario.trim() || null,
          permalink: postado ? undefined : permalink.trim() || null,
        },
      },
      {
        onSuccess: () => toast.success("Publicação salva."),
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar a publicação.")),
      },
    );
  }

  return (
    <section className="space-y-3" data-testid="secao-publicacao">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Publicação</h3>
        <Button
          size="sm"
          variant="outline"
          disabled={!roteiroCompleto || gerar.isPending}
          title={roteiroCompleto ? undefined : "Disponível quando o roteiro estiver completo."}
          onClick={gerarLegenda}
        >
          {gerar.isPending ? "Gerando…" : "Gerar legenda com IA"}
        </Button>
      </div>
      {erroGerar && (
        <p className="text-sm text-destructive" role="alert" data-testid="legenda-erro">
          {erroGerar}
        </p>
      )}
      <label className="block space-y-1 text-sm">
        <span>Legenda</span>
        <Textarea
          aria-label="Legenda"
          rows={6}
          value={legenda}
          onChange={(e) => setLegenda(e.target.value)}
        />
        <span
          className={legenda.length > LEGENDA_MAX ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
          data-testid="legenda-contador"
        >
          {legenda.length}/{LEGENDA_MAX}
        </span>
      </label>
      <label className="block space-y-1 text-sm">
        <span>Hashtags</span>
        <Textarea
          aria-label="Hashtags"
          rows={2}
          value={hashtags}
          onChange={(e) => setHashtags(e.target.value)}
        />
        <span
          className={tags.length > HASHTAGS_MAX ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
        >
          {tags.length}/{HASHTAGS_MAX}
        </span>
      </label>
      <label className="block space-y-1 text-sm">
        <span>Primeiro comentário</span>
        <Textarea
          aria-label="Primeiro comentário"
          rows={3}
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span>Permalink</span>
        <Input
          aria-label="Permalink"
          value={permalink}
          readOnly={postado}
          aria-invalid={!permalinkOk}
          placeholder="https://www.instagram.com/reel/..."
          onChange={(e) => setPermalink(e.target.value)}
        />
        {!permalinkOk && <span className="text-xs text-destructive">Use um link do instagram.com.</span>}
      </label>
      {post.postado_em && (
        <p className="text-xs text-muted-foreground" data-testid="postado-em">
          Postado em {new Date(post.postado_em).toLocaleString("pt-BR")}
        </p>
      )}
      <Button size="sm" disabled={excedeu || !permalinkOk || atualizar.isPending} onClick={salvar}>
        {atualizar.isPending ? "Salvando…" : "Salvar"}
      </Button>
    </section>
  );
}
