/**
 * One chat message of the unified chat (Estruturas contract §6.5 / §11.3). Assistant markdown goes
 * through the seed `MarkdownRenderer` (no raw HTML). An assistant `texto` message that carries
 * `propostas` renders them as cards (the SERVER parsed them — the client never derives headlines
 * from the text); a `roteiro_gerado` message renders the flow card. `(estrutura #N)` links open the
 * Estrutura detail, only for codes the message's own propostas vouch for.
 */
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Copy } from "lucide-react";
import { toast } from "sonner";
import { MarkdownRenderer } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Fluxo, Proposta } from "@/types/estruturas";
import type { Mencao } from "@/types/geracao";
import { codigoDoHref, linkarCitacoes } from "./citacoes";
import { FluxoCard } from "./FluxoCard";
import { estruturaUrl, PropostaCard } from "./PropostaCard";

interface Props {
  role: "user" | "assistant";
  conteudo: string;
  tipo?: "texto" | "roteiro_gerado";
  propostas?: Proposta[];
  fluxo?: Fluxo | null;
  referencias?: Mencao[];
  status?: "completa" | "parcial" | "erro";
  truncada?: boolean;
  streaming?: boolean;
  /** The proposta whose `escolher` is in flight, if any. */
  escolhendoId?: string | null;
  onEscolher?: (propostaId: string) => void;
}

async function copiar(texto: string) {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success("Copiado.");
  } catch {
    toast.error("Não foi possível copiar.");
  }
}

export function MensagemItem({
  role,
  conteudo,
  tipo = "texto",
  propostas = [],
  fluxo = null,
  referencias,
  status,
  truncada,
  streaming,
  escolhendoId = null,
  onEscolher,
}: Props) {
  const navigate = useNavigate();
  const assistente = role === "assistant";

  // code -> Estrutura id, from this message's own propostas (the only codes the server vouched for).
  const idPorCodigo = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of propostas) for (const e of p.estruturas) m.set(e.codigo, e.id);
    return m;
  }, [propostas]);
  const texto = useMemo(
    () => (assistente ? linkarCitacoes(conteudo, new Set(idPorCodigo.keys())) : conteudo),
    [assistente, conteudo, idPorCodigo],
  );

  if (assistente && tipo === "roteiro_gerado" && fluxo) {
    return (
      <article aria-label="Roteiro criado" className="flex flex-col items-start gap-2">
        {conteudo && <p className="text-sm text-muted-foreground">{conteudo}</p>}
        <FluxoCard fluxo={fluxo} tentando={escolhendoId === fluxo.proposta_id} onTentarDeNovo={(id) => onEscolher?.(id)} />
      </article>
    );
  }

  return (
    <article
      aria-label={assistente ? "Resposta da IA" : "Sua mensagem"}
      className={cn("flex flex-col gap-2", assistente ? "items-start" : "items-end")}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-4 py-3 text-sm",
          assistente ? "bg-muted" : "bg-primary text-primary-foreground",
        )}
      >
        {assistente ? (
          conteudo ? (
            <MarkdownRenderer
              content={texto}
              remoteImages="block"
              onNavigate={(href) => {
                const cod = codigoDoHref(href);
                const id = cod != null ? idPorCodigo.get(cod) : undefined;
                if (id) navigate(estruturaUrl(id));
              }}
            />
          ) : (
            <span className="text-muted-foreground">{streaming ? "Pensando..." : "(sem conteúdo)"}</span>
          )
        ) : (
          <p className="whitespace-pre-wrap">{conteudo}</p>
        )}
      </div>

      {!!referencias?.length && (
        <div className="flex flex-wrap gap-1">
          {referencias.map((r) => (
            <Badge key={`${r.tipo}:${r.id}`} variant="secondary">
              @{r.rotulo}
            </Badge>
          ))}
        </div>
      )}

      {assistente && status === "parcial" && (
        <p className="text-xs text-muted-foreground">Resposta interrompida (parcial).</p>
      )}
      {assistente && status === "erro" && (
        <p role="alert" className="text-xs text-destructive">A resposta terminou com erro.</p>
      )}
      {assistente && truncada && (
        <p className="text-xs text-muted-foreground">A resposta foi cortada por tamanho. Peça para continuar.</p>
      )}

      {assistente && conteudo && !streaming && (
        <Button type="button" size="sm" variant="ghost" onClick={() => void copiar(conteudo)}>
          <Copy className="mr-1 h-3.5 w-3.5" /> Copiar
        </Button>
      )}

      {assistente && !streaming && propostas.length > 0 && (
        <ul className="w-full max-w-[85%] space-y-2" aria-label="Headlines desta resposta">
          {propostas.map((p) => (
            <PropostaCard
              key={p.id}
              proposta={p}
              escolhendo={escolhendoId === p.id}
              bloqueada={!!escolhendoId && escolhendoId !== p.id}
              onEscolher={(id) => onEscolher?.(id)}
            />
          ))}
        </ul>
      )}
    </article>
  );
}
