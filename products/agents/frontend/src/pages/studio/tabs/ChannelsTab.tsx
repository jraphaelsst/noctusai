/**
 * Agent Studio — "Canais" (Lais page-0 agent `lead-imob`): the channel token
 * social-wiring uses, the LLM-key status hint for the version's provider, and
 * the READ-ONLY list of channel conversations (leads on WhatsApp etc.). There
 * is deliberately no composer: a channel conversation is driven by the
 * transport, never typed into from here.
 */
import { useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Link } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import { Badge, EmptyState } from "@noctusai/lib/design-system";
import { ChannelTokenCard } from "@/components/studio/ChannelTokenCard";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useChannelConversations, useChannelMessages } from "@/hooks/useChannel";
import { isProviderKeyConfigured, orgApiKeysHooks } from "@/hooks/useOrgApiKeys";
import { useAgentVersionRefs } from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { cn } from "@/lib/utils";

function fmt(value: string | null): string {
  return value ? format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "—";
}

function contactName(contact: Record<string, unknown> | null): string {
  const name = contact && typeof contact.nome === "string" ? contact.nome : null;
  return name ?? "Contato sem nome";
}

function KeyHint({ agentKey }: { agentKey: string }) {
  const refs = useAgentVersionRefs(agentKey);
  const keys = orgApiKeysHooks.useApiKeys();
  const target = refs.draft ?? refs.ativa;
  const provider = target?.provider ?? "anthropic";
  const configured = isProviderKeyConfigured(keys.data, provider);

  if (keys.showSkeleton || refs.showSkeleton) return <StudioLoading rows={1} testId="channel-key-hint-skeleton" />;
  if (keys.isError) return <StudioError error={keys.error} onRetry={() => void keys.refetch()} />;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-4 text-sm" data-testid="channel-key-hint">
      <span>
        Chave de IA ({provider === "openai" ? "OpenAI" : "Anthropic"}) da versão {target ? `v${target.versao}` : "—"}:
      </span>
      <Badge variant={configured ? "default" : "destructive"}>{configured ? "Configurada" : "Não configurada"}</Badge>
      {!configured && (
        <Link to="/chaves-ia" className="text-primary hover:underline">
          Configurar em Chaves de IA
        </Link>
      )}
    </div>
  );
}

function ConversationViewer({ conversationId }: { conversationId: string }) {
  const messages = useChannelMessages(conversationId);
  if (messages.showSkeleton) return <StudioLoading rows={3} testId="channel-messages-skeleton" />;
  if (messages.isError) return <StudioError error={messages.error} onRetry={messages.refetch} />;
  if (!messages.data || messages.data.length === 0) return <EmptyState message="Esta conversa ainda não tem mensagens." />;
  return (
    <ul className="space-y-2" data-testid="channel-messages" aria-label="Mensagens (somente leitura)">
      {messages.data.map((m) => (
        <li
          key={m.id}
          className={cn(
            "max-w-[85%] whitespace-pre-wrap rounded-lg border border-border p-2 text-sm",
            m.role === "assistant" ? "ml-auto bg-primary/10" : "bg-muted",
          )}
        >
          <p className="mb-0.5 text-[11px] text-muted-foreground">
            {m.role === "assistant" ? "Agente" : "Contato"} · {fmt(m.created_at)}
          </p>
          {m.texto}
        </li>
      ))}
    </ul>
  );
}

export default function ChannelsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const [channel, setChannel] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const conversations = useChannelConversations(agentKey, channel);

  return (
    <div className="space-y-4" data-testid="channels-tab">
      <KeyHint agentKey={agentKey} />
      <ChannelTokenCard agentKey={agentKey} isAdmin={isAdmin} />

      <section className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <MessageSquare className="h-4 w-4 text-primary" /> Conversas de canal (somente leitura)
            {conversations.isRefreshing && <span className="text-xs font-normal text-muted-foreground">Atualizando…</span>}
          </h2>
          <select
            aria-label="Filtrar por canal"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              setSelected(null);
            }}
            data-testid="channel-filter"
          >
            <option value="">Todos os canais</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </div>

        {!isAdmin ? (
          <EmptyState message="Somente administradores veem as conversas de canal." />
        ) : conversations.showSkeleton ? (
          <StudioLoading rows={3} testId="channel-conversations-skeleton" />
        ) : conversations.isError ? (
          <StudioError error={conversations.error} onRetry={conversations.refetch} />
        ) : !conversations.data || conversations.data.length === 0 ? (
          <EmptyState message="Nenhuma conversa de canal ainda." />
        ) : (
          <div className="grid gap-3 lg:grid-cols-[18rem_1fr]">
            <ul className="space-y-1" data-testid="channel-conversations">
              {conversations.data.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(c.id)}
                    data-testid={`channel-conversation-${c.id}`}
                    className={cn(
                      "w-full rounded-md border px-3 py-2 text-left text-sm",
                      selected === c.id ? "border-primary bg-primary/10" : "border-border hover:bg-muted",
                    )}
                  >
                    <p className="truncate font-medium">{contactName(c.contact)}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.channel ?? "canal"} · {fmt(c.last_message_at ?? c.created_at)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
            <div className="min-h-[8rem] rounded-md border border-border p-3">
              {selected ? <ConversationViewer conversationId={selected} /> : <EmptyState message="Selecione uma conversa." />}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
