/**
 * Library ↔ Esteira link (esteira-contract.md §3.4 / §6.3, FE-3): the "No post"
 * badge a bound headline/roteiro shows, and the "Criar post" action that turns
 * a library row into a post and opens it on the board. The library keeps every
 * row — the post only points at it.
 */
import { Link, useNavigate } from "react-router-dom";
import { FilePlus2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCriarPost, useVincularRoteiro } from "@/hooks/geracao/useEsteira";
import type { PostRef } from "@/types/geracao";
import { mensagemErro } from "./headlines/lote";

export const ESTEIRA_ROUTE = "/media-creation/esteira";
export const esteiraPostUrl = (postId: string) => `${ESTEIRA_ROUTE}?post=${encodeURIComponent(postId)}`;

/** "No post: <título> · <etapa>", linking to the Esteira with that post open. */
export function NoPostBadge({ post, className }: { post?: PostRef | null; className?: string }) {
  if (!post) return null;
  return (
    <Link to={esteiraPostUrl(post.id)} data-testid="no-post-badge" className={className}>
      <Badge variant="secondary">
        No post: {post.titulo} · {post.etapa_label}
      </Badge>
    </Link>
  );
}

function erroCriarPost(e: unknown): string {
  const bruto = e instanceof Error ? e.message : "";
  if (/headline_ja_em_post/.test(bruto) || /^\[409\]/.test(bruto)) return "Esta headline já está em um post.";
  return mensagemErro(e, "Não foi possível criar o post.");
}

interface CriarPostProps {
  marcaId: string | null;
  /** Bind this headline to the new post (§3.4). */
  headlineId?: string | null;
  /** Bind this roteiro to the new post after it is created (§3.6). */
  roteiroId?: string | null;
  /** Post title; defaults server-side to the headline text. */
  titulo?: string;
  /** Row already in a post: the action is not offered. */
  post?: PostRef | null;
  label?: string;
  ariaLabel?: string;
}

/** "Criar post": POST /posts {marca_id, headline_id?}, optional roteiro bind, then opens the post. */
export function CriarPostButton({
  marcaId,
  headlineId,
  roteiroId,
  titulo,
  post,
  label = "Criar post",
  ariaLabel,
}: CriarPostProps) {
  const navigate = useNavigate();
  const criar = useCriarPost();
  const vincular = useVincularRoteiro();
  const ocupado = criar.isPending || vincular.isPending;
  if (post) return null;

  async function onClick() {
    if (!marcaId) return;
    try {
      const novo = await criar.mutateAsync({
        marca_id: marcaId,
        ...(headlineId ? { headline_id: headlineId } : {}),
        ...(titulo ? { titulo } : {}),
      });
      if (roteiroId) {
        try {
          await vincular.mutateAsync({ postId: novo.id, roteiroId });
        } catch (e) {
          toast.error(`Post criado, mas o roteiro não foi vinculado: ${mensagemErro(e, "erro ao vincular.")}`);
        }
      }
      toast.success("Post criado na Esteira.");
      navigate(esteiraPostUrl(novo.id));
    } catch (e) {
      toast.error(erroCriarPost(e));
    }
  }

  return (
    <Button size="sm" variant="outline" aria-label={ariaLabel} disabled={!marcaId || ocupado} onClick={() => void onClick()}>
      <FilePlus2 className="mr-1 h-4 w-4" /> {ocupado ? "Criando…" : label}
    </Button>
  );
}
