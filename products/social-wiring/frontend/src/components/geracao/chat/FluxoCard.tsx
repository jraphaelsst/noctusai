/**
 * The `roteiro_gerado` message (Estruturas contract §9.2 / §11.3): the flow the server composed
 * for a chosen proposta — status, formato, the roteiro preview once written (per formato), the
 * Estruturas used, caption state and the links to the roteiro and the Esteira card.
 *
 * While the roteiro is being written `useRoteiro` polls it (jobPolling, ≤ 3 s, stops at a
 * terminal status). The state shown follows the roteiro's own live status so the card never
 * says "writing" after the roteiro finished; the messages read is refreshed at that moment so the
 * server-composed `fluxo` (legenda, card) catches up.
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Loader2 } from "lucide-react";
import { MarkdownRenderer } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CHAT_KEY } from "@/hooks/geracao/useChat";
import { useRoteiro } from "@/hooks/geracao/useRoteiros";
import { esteiraPostUrl } from "@/components/geracao/PostEsteira";
import type { EstruturaFormato, Fluxo, FluxoEtapa } from "@/types/estruturas";
import { estruturaUrl } from "./PropostaCard";
import { previewRoteiro } from "./roteiroPreview";
import { erroDoFluxo, ETAPA_ROTULO, FORMATO_ROTULO, LEGENDA_ROTULO } from "./rotulos";

export const HEADLINES_ROTEIROS_ROUTE = "/media-creation/chat/headlines-e-roteiros";

interface Props {
  fluxo: Fluxo;
  /** Starts the saga again (idempotent on the server): the retry of a failed flow. */
  onTentarDeNovo: (propostaId: string) => void;
  tentando: boolean;
}

function Preview({ formato, conteudo }: { formato: EstruturaFormato; conteudo: string }) {
  const p = previewRoteiro(formato, conteudo);
  if (p.tipo === "secoes") {
    return (
      <div className="space-y-2" data-testid="roteiro-preview" data-formato={formato}>
        <ol aria-label={p.rotulo} className="space-y-2">
          {p.secoes.map((s, i) => (
            <li key={`${s.titulo}-${i}`} className="rounded border bg-background p-2">
              <p className="text-xs font-semibold text-muted-foreground">{s.titulo}</p>
              <p className="whitespace-pre-wrap">{s.texto}</p>
            </li>
          ))}
        </ol>
        {p.legenda && (
          <div className="rounded border bg-background p-2">
            <p className="text-xs font-semibold text-muted-foreground">Legenda</p>
            <p className="whitespace-pre-wrap">{p.legenda}</p>
          </div>
        )}
      </div>
    );
  }
  return (
    <div data-testid="roteiro-preview" data-formato={formato}>
      <MarkdownRenderer content={p.texto} />
    </div>
  );
}

export function FluxoCard({ fluxo, onTentarDeNovo, tentando }: Props) {
  const qc = useQueryClient();
  const roteiroId = fluxo.roteiro?.id ?? null;
  const roteiroQ = useRoteiro(roteiroId);
  const roteiro = roteiroQ.data;

  const etapa: FluxoEtapa =
    roteiro?.status === "completo" ? "roteiro_pronto" : roteiro?.status === "falha" ? "falhou" : fluxo.etapa;

  // The roteiro left "writing" before the server-composed flow said so: refresh the messages once.
  const avisado = useRef<string | null>(null);
  useEffect(() => {
    const terminal = roteiro?.status === "completo" || roteiro?.status === "falha";
    if (terminal && fluxo.etapa === "roteiro_gerando" && avisado.current !== `${roteiro.id}:${roteiro.status}`) {
      avisado.current = `${roteiro.id}:${roteiro.status}`;
      void qc.invalidateQueries({ queryKey: [...CHAT_KEY, "mensagens"] });
    }
  }, [roteiro?.id, roteiro?.status, fluxo.etapa, qc]);

  const formato = fluxo.roteiro?.formato ?? null;
  const gerando = etapa === "roteiro_gerando" || etapa === "headline_salva";

  return (
    <section
      aria-label="Roteiro desta headline"
      data-etapa={etapa}
      className="w-full max-w-[85%] space-y-3 rounded-md border p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" data-testid="fluxo-etapa">
          {gerando && <Loader2 className="mr-1 h-3 w-3 animate-spin" aria-hidden />}
          {ETAPA_ROTULO[etapa]}
        </Badge>
        {formato && <Badge variant="secondary">{FORMATO_ROTULO[formato]}</Badge>}
        <span className="text-xs text-muted-foreground">{LEGENDA_ROTULO[fluxo.legenda]}</span>
      </div>

      <p className="font-medium">{fluxo.headline.texto}</p>

      {etapa === "falhou" && (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-destructive">
          <AlertTriangle className="h-4 w-4" aria-hidden />
          <span>{roteiro?.status === "falha" && roteiro.erro ? roteiro.erro : erroDoFluxo(fluxo.erro_codigo)}</span>
          <Button type="button" size="sm" variant="outline" disabled={tentando} onClick={() => onTentarDeNovo(fluxo.proposta_id)}>
            {tentando ? "Tentando..." : "Tentar de novo"}
          </Button>
        </div>
      )}

      {etapa === "roteiro_pronto" &&
        formato &&
        (roteiro?.conteudo ? (
          <Preview formato={formato} conteudo={roteiro.conteudo} />
        ) : roteiroQ.showSkeleton ? (
          <Skeleton className="h-16 w-full" data-testid="roteiro-preview-skeleton" />
        ) : roteiroQ.isError ? (
          <p role="alert" className="text-destructive">
            Não foi possível carregar o roteiro.{" "}
            <Button type="button" size="sm" variant="outline" onClick={() => void roteiroQ.refetch()}>
              Tentar novamente
            </Button>
          </p>
        ) : null)}

      {fluxo.estruturas.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Estruturas usadas</p>
          <ul className="space-y-1.5">
            {fluxo.estruturas.map((e) => (
              <li key={e.id} className="text-xs">
                <Link to={estruturaUrl(e.id)} className="font-medium underline-offset-2 hover:underline">
                  #{e.codigo} @{e.perfil.handle}
                </Link>
                {e.papel === "mistura" ? " (mistura)" : ""}
                {e.blocos.length > 0 && <span className="text-muted-foreground"> — {e.blocos.map((b) => b.nome).join(" · ")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <Link to={HEADLINES_ROTEIROS_ROUTE}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" aria-hidden /> Abrir roteiro
          </Link>
        </Button>
        {fluxo.post && (
          <Button asChild size="sm" variant="outline">
            <Link to={esteiraPostUrl(fluxo.post.id)}>
              <ExternalLink className="mr-1 h-3.5 w-3.5" aria-hidden /> Ver card{fluxo.post.etapa_label ? ` (${fluxo.post.etapa_label})` : ""}
            </Link>
          </Button>
        )}
      </div>
    </section>
  );
}
