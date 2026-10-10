import { Play } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import type { ExtracaoTipo, PostFonte } from "@/hooks/usePesquisaExtracao";
import { formatData, formatMetrica } from "./format";

interface PostCardProps {
  post: PostFonte;
  tipos: ExtracaoTipo[];
  selecionado: boolean;
  onToggle: (post: PostFonte) => void;
}

export const postKey = (p: Pick<PostFonte, "kind" | "account_id" | "id">) =>
  `${p.kind}:${p.account_id ?? ""}:${p.id}`;

function formatoBadge(post: PostFonte): string | null {
  const x = post.extra ?? {};
  if (post.kind === "youtube_video" && x.is_short === true) return "Short";
  if (post.kind === "instagram_media" && String(x.media_product_type ?? "").toUpperCase() === "REELS") return "Reels";
  if (x.formato === "Reels" || x.formato === "Short") return String(x.formato);
  return null;
}

export function PostCard({ post, tipos, selecionado, onToggle }: PostCardProps) {
  const formato = formatoBadge(post);
  const datas = tipos.map((t) => post.extraido?.[t]);
  const jaExtraido = tipos.length > 0 && datas.every((d) => !!d);
  const desabilitado = !post.analisavel;
  return (
    <div
      data-testid="post-card"
      title={desabilitado ? "Sem texto para analisar" : undefined}
      className={`flex flex-col gap-2 rounded-lg border p-3 text-sm ${
        desabilitado ? "opacity-50" : selecionado ? "border-primary bg-primary/5" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <Checkbox
          aria-label={`Selecionar post de ${formatData(post.published_at)}`}
          checked={selecionado}
          disabled={desabilitado}
          onCheckedChange={() => onToggle(post)}
        />
        {post.thumbnail_url ? (
          <img src={post.thumbnail_url} alt="" className="h-16 w-16 rounded object-cover" loading="lazy" />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded bg-muted">
            <Play className="h-5 w-5 text-muted-foreground" aria-hidden />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-xs text-muted-foreground">{formatData(post.published_at)}</span>
          <div className="flex flex-wrap gap-1">
            {formato && <Badge variant="secondary">{formato}</Badge>}
            {jaExtraido && (
              <Badge variant="outline" title={datas.map((d) => formatData(d)).join(" · ")}>
                Já extraído
              </Badge>
            )}
          </div>
        </div>
      </div>
      <p className="line-clamp-3 text-muted-foreground">{post.texto || "Sem texto"}</p>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Views {formatMetrica(post.plays)} · Likes {formatMetrica(post.likes)} · Comentários{" "}
          {formatMetrica(post.comments)}
        </span>
        {post.url && (
          <a href={post.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
            Ver post ↗
          </a>
        )}
      </div>
    </div>
  );
}
