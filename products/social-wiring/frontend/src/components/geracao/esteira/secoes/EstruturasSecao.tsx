/**
 * Post card, "Origem" section (estruturas-contract §6.8 / §11.3, FE-3): where the card came from —
 * headline, roteiro, the Estrutura(s) and their profile, the formato (any of the four), duração,
 * ordem do CTA, and the caption (editable through the existing post PATCH).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ROTULO_FORMATO } from "@/components/geracao/biblioteca/estruturas/rotulos";
import { mensagemEstruturas } from "@/components/geracao/biblioteca/estruturas/erros";
import { rotuloDuracao, rotuloOrdemCta } from "@/components/geracao/headlines-roteiros/rotulos";
import { StatusBadge } from "@/components/geracao/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAtualizarPost } from "@/hooks/geracao/useEsteira";
import { useOrigemDoCard } from "@/hooks/geracao/useHeadlinesRoteiros";
import type { EstruturaOrigemCard } from "@/types/estruturas";
import type { PostDetalhe } from "@/types/esteira";

const ORIGEM_LEGENDA = { ia: "Escrita pela IA", usuario: "Editada por você" } as const;

function Legenda({ postId, legenda }: { postId: string; legenda: EstruturaOrigemCard["legenda"] }) {
  const atualizar = useAtualizarPost();
  const [rascunho, setRascunho] = useState(legenda.texto ?? "");
  const sujo = rascunho !== (legenda.texto ?? "");

  function salvar() {
    atualizar.mutate(
      { id: postId, patch: { legenda: rascunho } },
      {
        onSuccess: () => toast.success("Legenda salva."),
        onError: (e) => toast.error(mensagemEstruturas(e, "Não foi possível salvar a legenda.")),
      },
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label htmlFor={`legenda-${postId}`} className="text-sm font-medium">
          Legenda
        </label>
        {legenda.origem && <Badge variant="outline">{ORIGEM_LEGENDA[legenda.origem]}</Badge>}
        {sujo && <Badge variant="secondary">Alterações não salvas</Badge>}
      </div>
      <Textarea id={`legenda-${postId}`} rows={5} value={rascunho} onChange={(e) => setRascunho(e.target.value)} />
      <Button size="sm" disabled={!sujo || atualizar.isPending} onClick={salvar}>
        {atualizar.isPending ? "Salvando…" : "Salvar legenda"}
      </Button>
    </div>
  );
}

export function EstruturasSecao({ post }: { post: PostDetalhe }) {
  const q = useOrigemDoCard(post.id);
  const o = q.data;

  if (q.showSkeleton) {
    return <div className="h-32 animate-pulse rounded bg-muted" data-testid="origem-loading" />;
  }
  if (q.isError && !o) {
    return (
      <p role="alert" className="text-sm text-destructive" data-testid="origem-erro">
        {mensagemEstruturas(q.error, "Não foi possível carregar a origem do card.")}
      </p>
    );
  }
  if (!o) return null;

  return (
    <div className="space-y-4 text-sm" data-testid="origem-secao" aria-busy={q.isRefreshing}>
      <section className="space-y-1">
        <h3 className="font-medium">Headline</h3>
        <p>{o.headline ? o.headline.texto : <span className="text-muted-foreground">Sem headline vinculada.</span>}</p>
      </section>

      <section className="space-y-1">
        <h3 className="font-medium">Roteiro</h3>
        {o.roteiro ? (
          <div className="flex flex-wrap items-center gap-2">
            <Link className="underline" to={`/media-creation/headlines-roteiros`} data-testid="origem-roteiro-link">
              {o.roteiro.nome}
            </Link>
            <StatusBadge status={o.roteiro.status} />
            <span className="text-muted-foreground">
              {rotuloDuracao(o.roteiro.duracao)} · CTA: {rotuloOrdemCta(o.roteiro.ordem_cta)} · v{o.roteiro.versao}
            </span>
          </div>
        ) : (
          <p className="text-muted-foreground">Sem roteiro vinculado.</p>
        )}
        {o.roteiro?.status === "completo" && (
          <p className="text-xs text-muted-foreground">Aguardando aprovação do roteiro.</p>
        )}
      </section>

      <section className="space-y-1">
        <h3 className="font-medium">Formato</h3>
        <p data-testid="origem-formato">{o.formato ? ROTULO_FORMATO[o.formato] : "—"}</p>
      </section>

      <section className="space-y-1">
        <h3 className="font-medium">Estruturas usadas</h3>
        {o.estruturas.length === 0 ? (
          <p className="text-muted-foreground">Nenhuma estrutura da biblioteca foi usada.</p>
        ) : (
          <ul className="space-y-1">
            {o.estruturas.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2">
                <Link to={`/media-creation/biblioteca/estruturas/${encodeURIComponent(e.id)}`}>
                  <Badge variant={e.papel === "principal" ? "default" : "outline"}>
                    #{e.codigo} · @{e.perfil.handle}
                  </Badge>
                </Link>
                <span className="text-muted-foreground">{e.formula_trecho}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {o.conversa && (
        <Link className="underline" to={`/media-creation/chat?conversa=${encodeURIComponent(o.conversa.id)}`}>
          Ver a conversa: {o.conversa.titulo || "Conversa"}
        </Link>
      )}

      <Legenda key={`${post.id}:${o.legenda.texto ?? ""}`} postId={post.id} legenda={o.legenda} />
    </div>
  );
}
