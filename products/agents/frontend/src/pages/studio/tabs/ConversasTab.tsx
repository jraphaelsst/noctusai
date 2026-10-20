/**
 * Agent Studio — "Conversas" (Julia v2 CONTRACT §5.3, §6): the lead threads of a channel agent for an
 * org ADMIN (LGPD: third-party personal data). Each line is labelled as the lead, the agent or a
 * human; system notices, tool calls and token usage are stripped server-side. Per-thread pause /
 * resume. Stage/score chips and violation counts render when the server provides `resultado`.
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Pause, Play } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState } from "@noctusai/lib/design-system";
import type { CanalConversa, MensagemThread, Participante, ThreadRole } from "@/api/studio/types-julia";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useAlterarParticipante, useCanalConversas, useThreadMensagens } from "@/hooks/studio/useCanalThreads";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

export function autorLabel(m: Pick<MensagemThread, "role" | "agent_nome">): string {
  const map: Record<ThreadRole, string> = { user: "Lead", assistant: "Agente", humano: "Humano", evento: "Evento" };
  return m.role === "assistant" && m.agent_nome ? `Agente · ${m.agent_nome}` : map[m.role];
}

export function ResultadoChips({ resultado }: { resultado: CanalConversa["resultado"] }) {
  if (!resultado) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="inline-flex flex-wrap gap-1" data-testid="resultado-chips">
      {resultado.estagio && <Badge variant="outline">Estágio: {resultado.estagio}</Badge>}
      {resultado.score !== null && <Badge variant="muted">Score {resultado.score}</Badge>}
      <Badge variant={resultado.violacoes > 0 ? "outline" : "muted"}>{resultado.violacoes} violação(ões)</Badge>
    </span>
  );
}

function contatoNome(c: CanalConversa): string {
  const nome = c.contact && typeof c.contact === "object" ? (c.contact as { nome?: unknown; name?: unknown }) : null;
  const v = nome?.nome ?? nome?.name;
  return typeof v === "string" && v ? v : (c.titulo ?? "Lead sem nome");
}

function Thread({ agentKey, conversa }: { agentKey: string; conversa: CanalConversa }) {
  const isAdmin = useIsAdmin();
  const msgs = useThreadMensagens(agentKey, conversa.id);
  const alterar = useAlterarParticipante(agentKey);
  const [estado, setEstado] = useState<Participante | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function mudar(para: "pausado" | "ativo") {
    setErro(null);
    try {
      const p = await alterar.mutateAsync({ threadId: conversa.id, input: { estado: para } });
      setEstado(p);
      toast.success(para === "pausado" ? "Agente pausado nesta conversa." : "Agente retomado nesta conversa.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-3" data-testid="conversa-thread">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{contatoNome(conversa)}</h3>
        <ResultadoChips resultado={conversa.resultado} />
        {estado && (
          <Badge variant={estado.estado === "ativo" ? "default" : "outline"} data-testid="conversa-estado">
            Agente: {estado.estado}
          </Badge>
        )}
        {isAdmin && (
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" disabled={alterar.isPending} onClick={() => mudar("pausado")} data-testid="conversa-pausar">
              <Pause className="mr-1 h-3.5 w-3.5" /> Pausar agente
            </Button>
            <Button size="sm" variant="outline" disabled={alterar.isPending} onClick={() => mudar("ativo")} data-testid="conversa-retomar">
              <Play className="mr-1 h-3.5 w-3.5" /> Retomar agente
            </Button>
          </div>
        )}
      </div>
      {erro && <p className="text-sm text-destructive" role="alert" data-testid="conversa-erro">{erro}</p>}

      {msgs.showSkeleton ? (
        <StudioLoading rows={3} />
      ) : msgs.isError ? (
        <StudioError error={msgs.error} onRetry={msgs.refetch} />
      ) : !msgs.data || msgs.data.length === 0 ? (
        <EmptyState message="Esta conversa ainda não tem mensagens." />
      ) : (
        <ol className="space-y-2" data-testid="conversa-mensagens">
          {msgs.isRefreshing && <li className="text-xs text-muted-foreground">Atualizando…</li>}
          {msgs.data.map((m) => (
            <li
              key={m.id}
              data-role={m.role}
              className={cn(
                "max-w-[85%] rounded-lg border px-3 py-2 text-sm",
                m.role === "user" ? "border-border bg-card" : m.role === "evento" ? "mx-auto border-dashed bg-muted/30 text-muted-foreground" : "ml-auto border-primary/30 bg-primary/5",
              )}
            >
              <p className="mb-0.5 text-[11px] font-semibold text-muted-foreground">{autorLabel(m)}</p>
              <p className="whitespace-pre-wrap">{m.texto}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function ConversasTab({ agentKey }: { agentKey: string }) {
  const [params, setParams] = useSearchParams();
  const lista = useCanalConversas(agentKey);
  const selecionada = params.get("conversa");

  if (lista.showSkeleton) return <StudioLoading rows={4} />;
  if (lista.isError) return <StudioError error={lista.error} onRetry={lista.refetch} />;
  const itens = lista.data ?? [];
  if (itens.length === 0) return <EmptyState message="Ainda não há conversas de leads com este agente." />;
  const atual = itens.find((c) => c.id === selecionada) ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]" data-testid="conversas-tab">
      <ul className="space-y-1" aria-label="Conversas">
        {lista.isRefreshing && <li className="text-xs text-muted-foreground">Atualizando…</li>}
        {itens.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              data-testid={`conversa-${c.id}`}
              onClick={() => setParams({ tab: "conversas", conversa: c.id })}
              className={cn("w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent", atual?.id === c.id ? "border-primary bg-accent" : "border-border")}
            >
              <span className="block font-medium">{contatoNome(c)}</span>
              <span className="block text-[11px] text-muted-foreground">{c.channel ?? "canal"} · {c.status}</span>
              <ResultadoChips resultado={c.resultado} />
            </button>
          </li>
        ))}
      </ul>
      <div>{atual ? <Thread key={atual.id} agentKey={agentKey} conversa={atual} /> : <EmptyState message="Selecione uma conversa." />}</div>
    </div>
  );
}
