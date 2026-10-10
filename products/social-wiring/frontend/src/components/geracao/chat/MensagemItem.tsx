/**
 * One chat message (contract §7.2). Assistant markdown goes through the seed
 * `MarkdownRenderer` (no raw HTML). HEADLINE answers add, per headline line:
 * "Salvar headline" (POST /headlines), "Criar roteiro a partir desta headline"
 * and "Criar roteiro com headline editável"; `(estrutura #N)` opens the viral.
 */
import { useMemo } from "react";
import { Copy, Star } from "lucide-react";
import { toast } from "sonner";
import { MarkdownRenderer } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Agente, Mencao } from "@/types/geracao";
import { codigoDoHref, extrairHeadlines, linkarCitacoes } from "./citacoes";

interface Props {
  role: "user" | "assistant";
  conteudo: string;
  agente: Agente;
  referencias?: Mencao[];
  status?: "completa" | "parcial" | "erro";
  truncada?: boolean;
  streaming?: boolean;
  /** Allowed `(estrutura #N)` codes, when the server sent them; otherwise the server resolves on click. */
  codigosPermitidos?: number[] | null;
  salvos: ReadonlySet<string>;
  salvando: boolean;
  onAbrirEstrutura: (codigo: number) => void;
  onSalvar: (texto: string) => void;
  /** `editavel`: opens the modal with the text as a free (unlinked) headline. */
  onCriarRoteiro: (texto: string, editavel: boolean) => void;
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
  agente,
  referencias,
  status,
  truncada,
  streaming,
  codigosPermitidos,
  salvos,
  salvando,
  onAbrirEstrutura,
  onSalvar,
  onCriarRoteiro,
}: Props) {
  const assistente = role === "assistant";
  const permitidos = useMemo(() => (codigosPermitidos ? new Set(codigosPermitidos) : null), [codigosPermitidos]);
  const texto = useMemo(
    () => (assistente && agente === "headline" ? linkarCitacoes(conteudo, permitidos) : conteudo),
    [assistente, agente, conteudo, permitidos],
  );
  const headlines = useMemo(
    () => (assistente && agente === "headline" && !streaming ? extrairHeadlines(conteudo) : []),
    [assistente, agente, conteudo, streaming],
  );

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
              onNavigate={(href) => {
                const cod = codigoDoHref(href);
                if (cod != null) onAbrirEstrutura(cod);
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

      {headlines.length > 0 && (
        <ul className="w-full max-w-[85%] space-y-2" aria-label="Headlines desta resposta">
          {headlines.map((h) => {
            const salvo = salvos.has(h);
            return (
              <li key={h} className="rounded-md border p-3 text-sm">
                <p className="mb-2">{h}</p>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" disabled={salvo || salvando} onClick={() => onSalvar(h)}>
                    <Star className="mr-1 h-3.5 w-3.5" />
                    {salvo ? "Headline salva" : "Salvar headline"}
                  </Button>
                  <Button type="button" size="sm" onClick={() => onCriarRoteiro(h, false)}>
                    Criar roteiro a partir desta headline
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => onCriarRoteiro(h, true)}>
                    Criar roteiro com headline editável
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}
