/**
 * Board card for one reel (esteira-contract.md §6.1 "Card face"). Presentational:
 * props in, one click out. The due pill reuses the seed `resolveDueState`,
 * except for posts already published or cancelled (never "overdue").
 */
import { resolveDueState } from "@noctusai/lib/components";
import { CheckSquare, Clock, MessageSquare } from "lucide-react";

import { StatusBadge } from "@/components/geracao/StatusBadge";
import { cn } from "@/lib/utils";
import type { PostCard } from "@/types/esteira";

export interface PostCardFaceProps {
  post: PostCard;
  /** Role of the column the card sits in (drives due-pill and motivo display). */
  papelEtapa?: string | null;
  /** Hide the marca chip when the board is already filtered by one marca. */
  esconderMarca?: boolean;
  isDragging?: boolean;
  onClick?: () => void;
}

const DUE_CLASSE = {
  done: "bg-emerald-500/20 text-emerald-600",
  overdue: "bg-red-500/20 text-red-600",
  soon: "bg-amber-500/20 text-amber-600",
  upcoming: "bg-secondary text-secondary-foreground",
} as const;

function dataCurta(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", { day: "numeric", month: "short" }).replace(".", "");
}

export function PostCardFace({ post, papelEtapa, esconderMarca, isDragging, onClick }: PostCardFaceProps) {
  const encerrado = papelEtapa === "postado" || papelEtapa === "cancelado";
  const due = post.data_entrega
    ? encerrado
      ? "done"
      : resolveDueState(post.data_entrega, post.entrega_concluida)
    : null;

  return (
    <div
      data-testid={`post-card-${post.id}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "cursor-pointer space-y-2 rounded-md border bg-card p-3 text-left transition-colors hover:border-primary/50",
        isDragging && "opacity-60",
      )}
    >
      {!esconderMarca && (
        <span className="inline-block rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          {post.marca_nome}
        </span>
      )}
      <p className="line-clamp-2 text-sm font-medium leading-snug">{post.titulo}</p>

      {post.headline ? (
        <p className="line-clamp-2 text-xs text-muted-foreground">{post.headline.texto}</p>
      ) : (
        <p className="text-xs italic text-muted-foreground">Sem headline</p>
      )}

      {post.roteiro && <StatusBadge status={post.roteiro.status} />}

      {papelEtapa === "cancelado" && post.motivo_bloqueio && (
        <p className="line-clamp-2 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {post.motivo_bloqueio}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {due && post.data_entrega && (
          <span
            data-testid={`post-card-${post.id}-due`}
            data-due={due}
            className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium", DUE_CLASSE[due])}
          >
            <Clock className="h-3 w-3" />
            {dataCurta(post.data_entrega)}
          </span>
        )}
        {post.checklist.total > 0 && (
          <span className="inline-flex items-center gap-1">
            <CheckSquare className="h-3 w-3" />
            {post.checklist.feitos}/{post.checklist.total}
          </span>
        )}
        {post.comentarios > 0 && (
          <span className="inline-flex items-center gap-1">
            <MessageSquare className="h-3 w-3" />
            {post.comentarios}
          </span>
        )}
        {post.membros.length > 0 && (
          <span className="ml-auto flex -space-x-1">
            {post.membros.map((m) => (
              <span
                key={m.id}
                title={m.nome}
                className="flex h-5 w-5 items-center justify-center rounded-full border border-background bg-primary/20 text-[10px] font-semibold"
                style={m.cor ? { backgroundColor: m.cor, color: "#fff" } : undefined}
              >
                {m.nome.slice(0, 1).toUpperCase()}
              </span>
            ))}
          </span>
        )}
      </div>
    </div>
  );
}
