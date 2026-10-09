/**
 * PropostasSection — the atendimento's propostas on the Geral tab (CONTRACT
 * §4.3). Click a card → `PropostaModal`. Creation happens from a visited
 * roteiro item ("Gerar proposta", S3), not here.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { usePropostas } from "@/hooks/usePropostas";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { CardSubpageKey } from "@/components/card/cardSubpages";

import { PropostaCard } from "./PropostaCard";
import { PropostaModal } from "./PropostaModal";

export interface PropostasSectionProps {
  clienteId: string;
  /** Switches the card to another subpage (Contratos / Certidões). */
  irPara?: (subpage: CardSubpageKey) => void;
}

export function PropostasSection({ clienteId, irPara }: PropostasSectionProps) {
  const query = usePropostas(clienteId);
  const [aberta, setAberta] = useState<string | null>(null);
  const items = query.data ?? [];

  return (
    <section className="space-y-2" data-testid="propostas-section">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">Propostas</h3>
        {query.isRefreshing && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" data-testid="propostas-refreshing" />
        )}
      </div>
      {query.showSkeleton ? (
        <p className="text-sm text-muted-foreground" data-testid="propostas-loading">Carregando…</p>
      ) : query.isError && !query.data ? (
        <p className="text-sm text-destructive" role="alert" data-testid="propostas-erro">
          {mensagemErroServidor(query.error, "Não foi possível carregar as propostas.")}
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="propostas-vazio">
          Nenhuma proposta ainda. Gere uma a partir de uma visita realizada na aba Roteiros.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <PropostaCard key={p.id} proposta={p} onClick={() => setAberta(p.id)} />
          ))}
        </div>
      )}
      {aberta && (
        <PropostaModal
          clienteId={clienteId}
          propostaId={aberta}
          onClose={() => setAberta(null)}
          irPara={irPara}
        />
      )}
    </section>
  );
}
