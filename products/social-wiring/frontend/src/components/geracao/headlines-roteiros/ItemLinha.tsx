/**
 * One row of "Headlines e Roteiros" (estruturas-contract §6.9 / §11.3): headline, linked roteiro
 * (status, formato, ordem do CTA, duração, versão, approval badge once S3 lands), Estrutura chips,
 * source conversation, card, and the actions that reuse the existing mutations.
 *
 * The approval badge is HIDDEN while `roteiro.aprovacao === null` (S3 not landed / roteiro not submitted).
 */
import { Heart, MessageSquare, Pencil, RefreshCw, ScrollText, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { CriarPostButton, NoPostBadge } from "@/components/geracao/PostEsteira";
import { STATUS_ROTULO } from "@/components/geracao/labels";
import { StatusBadge } from "@/components/geracao/StatusBadge";
import { ROTULO_FORMATO } from "@/components/geracao/biblioteca/estruturas/rotulos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { dataPtBr } from "@/components/pesquisa/format";
import type { HeadlineRoteiroItem } from "@/types/estruturas";
import { ROTULO_APROVACAO, rotuloDuracao, rotuloOrdemCta, textoDoItem } from "./rotulos";

export interface ItemLinhaProps {
  item: HeadlineRoteiroItem;
  marcaId: string | null;
  ocupado?: boolean;
  onFavoritar: (headlineId: string, favoritar: boolean) => void;
  onEditarHeadline: (item: HeadlineRoteiroItem) => void;
  onAbrirRoteiro: (roteiroId: string) => void;
  onCriarRoteiro: (item: HeadlineRoteiroItem) => void;
  onReprocessar: (roteiroId: string) => void;
  onExcluir: (item: HeadlineRoteiroItem) => void;
}

export function ItemLinha({
  item,
  marcaId,
  ocupado,
  onFavoritar,
  onEditarHeadline,
  onAbrirRoteiro,
  onCriarRoteiro,
  onReprocessar,
  onExcluir,
}: ItemLinhaProps) {
  const { headline, roteiro, estruturas, conversa, post } = item;
  const texto = textoDoItem(item);
  const rotulo = texto.length > 60 ? `${texto.slice(0, 60)}…` : texto;

  return (
    <li className="space-y-2 rounded-lg border p-4" data-testid="hr-item">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="font-medium">{texto}</p>
          <p className="text-xs text-muted-foreground">
            {dataPtBr(item.created_at)}
            {headline?.acima_recomendado && <span className="ml-2 text-warning-foreground">Acima do tamanho recomendado</span>}
            {!headline && <span className="ml-2">Roteiro sem headline salva</span>}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          {headline && (
            <>
              <Button
                size="icon"
                variant="ghost"
                aria-label={headline.favorita ? `Desfavoritar ${rotulo}` : `Favoritar ${rotulo}`}
                aria-pressed={headline.favorita}
                disabled={ocupado}
                onClick={() => onFavoritar(headline.id, !headline.favorita)}
              >
                <Heart className={headline.favorita ? "h-4 w-4 fill-current text-destructive" : "h-4 w-4"} />
              </Button>
              <Button size="icon" variant="ghost" aria-label={`Editar headline ${rotulo}`} onClick={() => onEditarHeadline(item)}>
                <Pencil className="h-4 w-4" />
              </Button>
            </>
          )}
          <Button size="icon" variant="ghost" aria-label={`Excluir ${rotulo}`} disabled={ocupado} onClick={() => onExcluir(item)}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {roteiro ? (
        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="hr-roteiro">
          <ScrollText className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="font-medium">{roteiro.nome}</span>
          {roteiro.status in STATUS_ROTULO ? (
            <StatusBadge status={roteiro.status} />
          ) : (
            <Badge variant="outline" data-testid="hr-status-desconhecido">
              Em andamento
            </Badge>
          )}
          <Badge variant="secondary" data-testid="hr-formato">
            {ROTULO_FORMATO[roteiro.formato]}
          </Badge>
          <span className="text-muted-foreground">CTA: {rotuloOrdemCta(roteiro.ordem_cta)}</span>
          <span className="text-muted-foreground">{rotuloDuracao(roteiro.duracao)}</span>
          <span className="text-muted-foreground">v{roteiro.versao}</span>
          {roteiro.aprovacao && (
            <Badge variant="outline" data-testid="hr-aprovacao" data-estado={roteiro.aprovacao.estado}>
              {ROTULO_APROVACAO[roteiro.aprovacao.estado]}
            </Badge>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="hr-sem-roteiro">
          Esta headline ainda não tem roteiro.
        </p>
      )}

      {estruturas.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label="Estruturas usadas">
          {estruturas.map((e) => (
            <li key={e.id}>
              <Link to={`/media-creation/biblioteca/estruturas/${encodeURIComponent(e.id)}`} title={e.formula_trecho}>
                <Badge variant={e.papel === "principal" ? "default" : "outline"}>
                  @{e.perfil.handle} · #{e.codigo}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {roteiro && (
          <Button size="sm" variant="outline" onClick={() => onAbrirRoteiro(roteiro.id)}>
            Abrir roteiro
          </Button>
        )}
        {roteiro && roteiro.status !== "criando" && roteiro.status !== "processando" && (
          <Button size="sm" variant="ghost" disabled={ocupado} onClick={() => onReprocessar(roteiro.id)}>
            <RefreshCw className="mr-1 h-3 w-3" /> Reprocessar
          </Button>
        )}
        {!roteiro && headline && (
          <Button size="sm" variant="outline" onClick={() => onCriarRoteiro(item)}>
            Criar roteiro
          </Button>
        )}
        {conversa && (
          <Link
            className="inline-flex items-center gap-1 text-sm underline"
            to={`/media-creation/chat?conversa=${encodeURIComponent(conversa.id)}`}
          >
            <MessageSquare className="h-3 w-3" /> {conversa.titulo || "Conversa"}
          </Link>
        )}
        {post ? (
          <NoPostBadge post={post} />
        ) : (
          roteiro?.status === "completo" && (
            <CriarPostButton
              marcaId={marcaId}
              headlineId={headline?.id ?? null}
              roteiroId={roteiro.id}
              titulo={roteiro.nome}
              ariaLabel={`Criar post de ${roteiro.nome}`}
            />
          )
        )}
      </div>
    </li>
  );
}
