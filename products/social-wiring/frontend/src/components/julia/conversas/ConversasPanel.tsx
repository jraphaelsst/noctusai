/**
 * Julia › Conversas v2 body for one connection: tabs (Todas · Minhas ·
 * Arquivadas), search, "Filtro de conversas" drawer, list | kanban toggle
 * (`?view=kanban`), the seed ChatWindow fed with the server-filtered rows, and
 * the "Cliente" column for the open conversation.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Columns3, Filter, List, Search } from "lucide-react";
import type { ChatThread } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { WhatsAppChatWindow, ThreadsFeedContext, type ThreadsFeed } from "@/components/WhatsAppChatWindow";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  CONVERSAS_KEY, FILTROS_VAZIOS, contarFiltros, useJuliaConversas,
  type Aba, type Conversa, type FiltrosConversas,
} from "@/hooks/useJuliaConversas";
import { useWhatsAppChats } from "@/hooks/useWhatsAppChats";
import { useQueryClient } from "@tanstack/react-query";
import { ClienteColumn } from "./ClienteColumn";
import { OptOutAviso } from "@/components/julia/optouts/OptOutConversa";
import { ConversasKanban } from "./ConversasKanban";
import { FiltroConversasDrawer } from "./FiltroConversasDrawer";

const ABAS: { key: Aba; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "minhas", label: "Minhas" },
  { key: "arquivadas", label: "Arquivadas" },
];

export function conversaParaThread(c: Conversa): ChatThread {
  return {
    id: c.chat_id,
    title: c.nome,
    lastMessagePreview: c.ultima_mensagem ?? null,
    lastMessageAt: c.ultima_mensagem_at ?? null,
    lastDirection: c.direcao ?? null,
    unreadCount: c.nao_lidas ?? 0,
    meta: {
      agente_pausado: c.agente_pausado === true,
      contato_id: c.contato_id,
      arquivado: c.arquivado === true,
      bloqueado: c.bloqueado === true,
      responsavel_user_id: c.responsavel_user_id ?? null,
    },
  };
}

interface Props { connectionId: string; autoReplyEnabled: boolean }

export function ConversasPanel({ connectionId, autoReplyEnabled }: Props) {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "kanban" ? "kanban" : "lista";
  const [aba, setAba] = useState<Aba>("todas");
  const [busca, setBusca] = useState("");
  const [filtros, setFiltros] = useState<FiltrosConversas>(FILTROS_VAZIOS);
  const [drawer, setDrawer] = useState(false);
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const qc = useQueryClient();

  const q = useDebouncedValue(busca, 300);
  const efetivos = useMemo(() => ({ ...filtros, q }), [filtros, q]);
  const lista = useJuliaConversas(aba, efetivos, view === "lista");

  // The WAHA chat cache is patched in place by the realtime stream; a bump there
  // means a new message / read-state, so the server-filtered list is stale.
  const { dataUpdatedAt } = useWhatsAppChats(connectionId);
  useEffect(() => {
    if (dataUpdatedAt) void qc.invalidateQueries({ queryKey: CONVERSAS_KEY });
  }, [dataUpdatedAt, qc]);

  const showSkeleton = lista.isPending && !lista.data;
  const conversas = lista.data ?? [];
  const feed: ThreadsFeed = useMemo(
    () => ({ data: conversas.map(conversaParaThread), isLoading: showSkeleton, isError: lista.isError && !lista.data }),
    [conversas, showSkeleton, lista.isError, lista.data],
  );
  const atual = conversas.find((c) => c.chat_id === selecionado) ?? null;
  const nFiltros = contarFiltros(filtros);

  function setView(v: "lista" | "kanban") {
    const next = new URLSearchParams(params);
    if (v === "kanban") next.set("view", "kanban"); else next.delete("view");
    setParams(next, { replace: true });
  }

  return (
    <div className="space-y-3" data-testid="conversas-panel">
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Conversas" className="inline-flex rounded-md border p-0.5">
          {ABAS.map((a) => (
            <button key={a.key} type="button" role="tab" aria-selected={aba === a.key} disabled={view === "kanban"}
              onClick={() => setAba(a.key)} data-testid={`aba-${a.key}`}
              className={"rounded px-3 py-1 text-sm disabled:opacity-50 " + (aba === a.key && view === "lista" ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
              {a.label}
            </button>
          ))}
        </div>
        <div className="relative min-w-48 flex-1 max-w-xs">
          <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
          <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar conversas" aria-label="Buscar conversas" className="h-8 pl-8" />
        </div>
        <Button variant="outline" size="sm" className="gap-1" onClick={() => setDrawer(true)} data-testid="filtro-abrir">
          <Filter className="h-4 w-4" /> Filtros{nFiltros > 0 ? ` (${nFiltros})` : ""}
        </Button>
        <div className="ml-auto inline-flex rounded-md border p-0.5">
          <Button variant={view === "lista" ? "default" : "ghost"} size="sm" className="h-7 gap-1" onClick={() => setView("lista")} aria-pressed={view === "lista"} data-testid="view-lista">
            <List className="h-4 w-4" /> Ver como lista
          </Button>
          <Button variant={view === "kanban" ? "default" : "ghost"} size="sm" className="h-7 gap-1" onClick={() => setView("kanban")} aria-pressed={view === "kanban"} data-testid="view-kanban">
            <Columns3 className="h-4 w-4" /> Ver como kanban
          </Button>
        </div>
      </div>

      {view === "kanban" ? (
        <ConversasKanban filtros={efetivos} onAbrir={(c) => { setSelecionado(c.chat_id); setView("lista"); }} />
      ) : (
        <>
        {selecionado && <OptOutAviso connectionId={connectionId} chatId={selecionado} />}
        <div className="flex h-[calc(100vh-21rem)] min-h-[28rem] rounded-md border" data-refreshing={lista.isFetching && !!lista.data ? "true" : "false"}>
          <ThreadsFeedContext.Provider value={feed}>
            <WhatsAppChatWindow
              connectionId={connectionId}
              autoReplyEnabled={autoReplyEnabled}
              className="min-w-0 flex-1"
              selectedThreadId={selecionado}
              onSelectThread={setSelecionado}
            />
          </ThreadsFeedContext.Provider>
          {atual && <div className="hidden lg:flex"><ClienteColumn key={atual.contato_id} contatoId={atual.contato_id} nome={atual.nome} etiquetas={atual.etiquetas ?? []} credito={atual.credito ?? null} /></div>}
        </div>
        </>
      )}

      {drawer && <FiltroConversasDrawer filtros={filtros} onAplicar={setFiltros} onClose={() => setDrawer(false)} />}
    </div>
  );
}
