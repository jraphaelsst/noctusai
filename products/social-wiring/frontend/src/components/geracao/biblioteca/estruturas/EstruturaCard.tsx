/**
 * One Estrutura in a list: formula, profile, formato, objetivos, blocks count, source video.
 * Admin-only badges (status other than `ativa`, "Pendente de revisão") render only when the server sent
 * the field — a member's response never carries `pendente_revisao` and never a non-`ativa` row.
 */
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import type { EstruturaResumo } from "@/types/estruturas";
import { AtribuicaoIAChip, RevisaoDesusoBadge } from "./atribuicao";
import { ROTULO_FORMATO, ROTULO_OBJETIVO, ROTULO_STATUS, rotuloCodigo } from "./rotulos";

export const rotaEstrutura = (id: string) => `/media-creation/biblioteca/estruturas/${encodeURIComponent(id)}`;

export function EstruturaCard({ estrutura: e }: { estrutura: EstruturaResumo }) {
  return (
    <article
      className="relative flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-xs transition-colors focus-within:ring-2 focus-within:ring-ring hover:border-primary/50"
      data-testid={`estrutura-card-${e.id}`}
    >
      <div className="flex items-start gap-3">
        {e.viral?.thumbnail_url ? (
          <img src={e.viral.thumbnail_url} alt="" loading="lazy" className="h-16 w-9 shrink-0 rounded object-cover" />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            {rotuloCodigo(e.codigo)} · @{e.perfil.handle}
          </p>
          <h3 className="line-clamp-3 text-sm font-medium">
            {/* The stretched link makes the whole card one target; the heading keeps the accessible name. */}
            <Link to={rotaEstrutura(e.id)} className="after:absolute after:inset-0 focus-visible:outline-hidden">
              {e.formula_headline}
            </Link>
          </h3>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {e.formato ? <Badge variant="secondary">{ROTULO_FORMATO[e.formato]}</Badge> : <Badge variant="outline">Sem formato</Badge>}
        {e.objetivos.map((o) => (
          <Badge key={o} variant="outline">
            {ROTULO_OBJETIVO[o]}
          </Badge>
        ))}
        <span className="text-xs text-muted-foreground">{e.blocos_total === 1 ? "1 bloco" : `${e.blocos_total} blocos`}</span>
      </div>
      {(e.status !== "ativa" || e.pendente_revisao || e.revisao_por_desuso || e.gerada_por_ia || e.selecionada_pela_marca) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {e.status !== "ativa" && <Badge variant={e.status === "rascunho" ? "default" : "secondary"}>{ROTULO_STATUS[e.status]}</Badge>}
          {e.pendente_revisao && (
            <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 font-normal text-amber-800 dark:text-amber-300">
              Pendente de revisão
            </Badge>
          )}
          <RevisaoDesusoBadge desde={e.revisao_por_desuso} />
          <AtribuicaoIAChip gerada={e.gerada_por_ia} handle={e.perfil.handle} />
          {e.selecionada_pela_marca && <Badge variant="outline">Na sua biblioteca</Badge>}
        </div>
      )}
    </article>
  );
}
