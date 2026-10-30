/**
 * Lead slot panel for a Conversas thread (contract wave 2): operação + each
 * ACTIVE essential question → its value or "—", qualificatória marked.
 * Questions switched off are hidden (their stored values are kept server-side).
 * Mounted through the `ThreadHeaderExtra` seam (JuliaThreadHeader) as a popover.
 */
import { ClipboardList, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useJuliaContato, useJuliaPerguntas } from "@/hooks/useJuliaPerguntas";

const OPERACAO: Record<string, string> = {
  compra: "Compra",
  aluguel: "Aluguel",
  administracao: "Administração",
};

export function PainelLeadConteudo({ connectionId, chatId }: { connectionId: string; chatId: string }) {
  const contato = useJuliaContato(connectionId, chatId);
  const perguntas = useJuliaPerguntas();
  const showSkeleton = (contato.isPending && !contato.data) || (perguntas.isPending && !perguntas.data);

  if (showSkeleton) {
    return <div className="h-24 animate-pulse rounded bg-muted" data-testid="painel-lead-skeleton" />;
  }
  if (contato.isError && !contato.data) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="painel-lead-erro">
        Sem dados da Julia para esta conversa.
      </p>
    );
  }
  const d = contato.data;
  const op = d?.interacao_atual?.operacao ?? d?.contato?.operacao ?? null;
  const ativas = (perguntas.data?.catalogo ?? []).filter((p) => p.ativa);
  const slots = d?.slots ?? {};
  return (
    <dl className="space-y-2 text-sm" data-testid="painel-lead">
      <div className="flex justify-between gap-3" data-testid="painel-operacao">
        <dt className="text-muted-foreground">Operação</dt>
        <dd className="font-medium">{(op && OPERACAO[op]) || "—"}</dd>
      </div>
      {perguntas.isError && !perguntas.data ? (
        <p className="text-xs text-destructive" data-testid="painel-perguntas-erro">
          Não foi possível carregar as perguntas.
        </p>
      ) : (
        ativas.length === 0 && <p className="text-xs text-muted-foreground">Nenhuma pergunta ativa.</p>
      )}
      {ativas.map((p) => {
        const v = slots[p.chave];
        const vazio = v === undefined || v === null || v === "";
        return (
          <div key={p.chave} className="flex justify-between gap-3" data-testid={`painel-slot-${p.chave}`}>
            <dt className="flex items-center gap-1 text-muted-foreground">
              {p.qualificatoria && (
                <Star className="h-3 w-3 fill-warning text-warning-foreground" aria-label="Qualificatória" />
              )}
              {p.label}
            </dt>
            <dd className="font-medium">{vazio ? "—" : String(v)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

export function PainelLead({ connectionId, chatId }: { connectionId: string | null; chatId: string }) {
  if (!connectionId) return null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs" data-testid="painel-lead-abrir">
          <ClipboardList className="mr-1 h-3 w-3" /> Dados do lead
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="end">
        <PainelLeadConteudo connectionId={connectionId} chatId={chatId} />
      </PopoverContent>
    </Popover>
  );
}
