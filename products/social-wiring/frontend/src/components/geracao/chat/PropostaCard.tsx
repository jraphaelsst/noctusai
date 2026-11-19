/**
 * One headline the assistant proposed (Estruturas contract §6.5 / §11.3): the text, the
 * attention-trigger tag, the Estrutura chip(s) it came from (`#codigo @handle`, each opening
 * the Estrutura detail) and "Criar roteiro", which writes the roteiro right away.
 */
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Loader2, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FORMATO_ROTULO } from "./rotulos";
import type { Proposta } from "@/types/estruturas";

export const estruturaUrl = (id: string) => `/media-creation/biblioteca/estruturas/${encodeURIComponent(id)}`;

interface Props {
  proposta: Proposta;
  /** This proposta's `escolher` request is in flight. */
  escolhendo: boolean;
  /** Another proposta of the conversation is being created: only one flow starts at a time. */
  bloqueada: boolean;
  onEscolher: (propostaId: string) => void;
}

export function PropostaCard({ proposta, escolhendo, bloqueada, onEscolher }: Props) {
  const escolhida = proposta.status === "escolhida";
  const mistura = proposta.estruturas.length > 1;
  const roteiro = proposta.tipo === "roteiro";
  const [aberto, setAberto] = useState(false);
  const roteiroId = useId();
  return (
    <li className="rounded-md border p-3 text-sm" data-proposta-id={proposta.id} data-tipo={roteiro ? "roteiro" : "headline"}>
      {roteiro ? (
        <div className="mb-2 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{proposta.titulo}</p>
            {proposta.formato && <Badge variant="secondary">{FORMATO_ROTULO[proposta.formato]}</Badge>}
          </div>
          <p
            id={roteiroId}
            data-testid="roteiro-script"
            className={`whitespace-pre-wrap break-words text-muted-foreground ${aberto ? "" : "line-clamp-6"}`}
          >
            {proposta.texto}
          </p>
          <Button type="button" size="sm" variant="link" className="h-auto p-0" aria-expanded={aberto} aria-controls={roteiroId} onClick={() => setAberto((v) => !v)}>
            {aberto ? "Recolher" : "Ver roteiro completo"}
          </Button>
        </div>
      ) : (
        <p className="mb-2 font-medium">{proposta.texto}</p>
      )}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {proposta.gatilho_tag && <Badge variant="outline">{proposta.gatilho_tag}</Badge>}
        {proposta.estruturas.length === 0 ? (
          <span className="text-xs text-muted-foreground">Sem estrutura da Biblioteca</span>
        ) : (
          <>
            <span className="text-xs text-muted-foreground">{mistura ? "Mistura de:" : "Estrutura:"}</span>
            {proposta.estruturas.map((e) => (
              <Link
                key={e.id}
                to={estruturaUrl(e.id)}
                aria-label={`Abrir a estrutura #${e.codigo} de @${e.perfil.handle}`}
                className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2 py-0.5 text-xs hover:bg-muted"
              >
                <Sparkles className="h-3 w-3" aria-hidden />#{e.codigo} @{e.perfil.handle}
                {mistura && e.principal && <span className="text-muted-foreground">(principal)</span>}
              </Link>
            ))}
          </>
        )}
      </div>
      <Button
        type="button"
        size="sm"
        variant={escolhida ? "outline" : "default"}
        disabled={escolhida || escolhendo || bloqueada}
        onClick={() => onEscolher(proposta.id)}
      >
        {escolhendo ? (
          <>
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden /> {roteiro ? "Salvando roteiro..." : "Criando roteiro..."}
          </>
        ) : escolhida ? (
          <>
            <Check className="mr-1 h-3.5 w-3.5" aria-hidden /> {roteiro ? "Roteiro escolhido" : "Roteiro criado"}
          </>
        ) : roteiro ? (
          "Usar este roteiro"
        ) : (
          "Criar roteiro"
        )}
      </Button>
    </li>
  );
}
