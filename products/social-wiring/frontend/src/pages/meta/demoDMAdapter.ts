/**
 * demoDMAdapter — a seeded, in-memory ChatWindow adapter for the Instagram
 * DMs screencast required by Meta App Review.
 *
 * WHY THIS EXISTS: `instagram_manage_messages` sits at Standard Access, where
 * Meta blocks every conversations call against a non-app-role user (see
 * `meta_dms_router` / the -2/2534084 + 200/2534048 gate). So the real inbox
 * can't be shown BEFORE Advanced Access is granted — a chicken-and-egg that
 * Meta resolves by accepting a clear feature demonstration. This adapter drives
 * the exact same `<ChatWindow>` the live Meta-DM adapter does (thread list →
 * open thread → read → compose + send), but from deterministic seeded data, so
 * the reviewer sees the real UX. It is DEMO-ONLY: reachable solely via the
 * `?demo=1` query param on the DMs tab, never wired into the live data path,
 * and it performs NO network calls (no writes to Instagram).
 */
import { useSyncExternalStore } from "react";

import type {
  ChatMessage,
  ChatThread,
  ChatWindowAdapter,
} from "@noctusai/lib/design-system";

interface DemoThread extends ChatThread {
  messages: ChatMessage[];
}

// ─── Seed (a realtor consultancy inbox, pt-BR) ───────────────────────────────

function seed(): Record<string, DemoThread> {
  const threads: DemoThread[] = [
    {
      id: "demo-1",
      title: "Marina Alves",
      lastMessagePreview: "Perfeito, obrigada! Fico no aguardo 😊",
      lastMessageAt: "2026-07-28T13:42:00Z",
      lastDirection: "inbound",
      unreadCount: 2,
      messages: [
        { id: "d1-1", direction: "inbound", body: "Oi! Vi o anúncio do apartamento de 2 quartos no Jardim Europa, ainda está disponível?", created_at: "2026-07-28T13:20:00Z" },
        { id: "d1-2", direction: "outbound", body: "Olá, Marina! Está sim 🙂 É um 2 quartos com suíte, 68m², uma vaga. Quer agendar uma visita?", created_at: "2026-07-28T13:31:00Z" },
        { id: "d1-3", direction: "inbound", body: "Quero! Consigo ir no sábado de manhã?", created_at: "2026-07-28T13:40:00Z" },
        { id: "d1-4", direction: "inbound", body: "Perfeito, obrigada! Fico no aguardo 😊", created_at: "2026-07-28T13:42:00Z" },
      ],
    },
    {
      id: "demo-2",
      title: "Carlos Mendes",
      lastMessagePreview: "Qual o valor do condomínio?",
      lastMessageAt: "2026-07-28T12:15:00Z",
      lastDirection: "inbound",
      unreadCount: 1,
      messages: [
        { id: "d2-1", direction: "inbound", body: "Boa tarde, tenho interesse na cobertura da Vila Nova.", created_at: "2026-07-28T12:05:00Z" },
        { id: "d2-2", direction: "outbound", body: "Boa tarde, Carlos! Ótima escolha. Posso te enviar o book completo com fotos e planta?", created_at: "2026-07-28T12:10:00Z" },
        { id: "d2-3", direction: "inbound", body: "Pode sim. Qual o valor do condomínio?", created_at: "2026-07-28T12:15:00Z" },
      ],
    },
    {
      id: "demo-3",
      title: "Juliana Rocha",
      lastMessagePreview: "Vocês trabalham com financiamento pela Caixa?",
      lastMessageAt: "2026-07-27T18:50:00Z",
      lastDirection: "inbound",
      unreadCount: 0,
      messages: [
        { id: "d3-1", direction: "inbound", body: "Oi, vocês trabalham com financiamento pela Caixa?", created_at: "2026-07-27T18:50:00Z" },
      ],
    },
  ];
  return Object.fromEntries(threads.map((t) => [t.id, t]));
}

// ─── Minimal external store (send appends live for the recording) ────────────

let _threads: Record<string, DemoThread> = seed();
const _listeners = new Set<() => void>();
let _snapshot = _threads; // stable reference; swapped on mutation

function emit() {
  _snapshot = { ..._threads };
  _listeners.forEach((l) => l());
}
function subscribe(cb: () => void) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}
function getSnapshot() {
  return _snapshot;
}

function useStore() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

// ─── Adapter ─────────────────────────────────────────────────────────────────

export const demoDMAdapter: ChatWindowAdapter = {
  useThreads: () => {
    const store = useStore();
    const data = Object.values(store)
      .sort((a, b) => (b.lastMessageAt ?? "").localeCompare(a.lastMessageAt ?? ""))
      .map(({ messages: _messages, ...thread }) => thread);
    return { data, isLoading: false, isError: false };
  },

  useMessages: (_scopeId, threadId) => {
    const store = useStore();
    const data = threadId ? store[threadId]?.messages ?? [] : [];
    return { data, isLoading: false, isError: false };
  },

  useSend: (_scopeId, threadId) => ({
    isPending: false,
    mutateAsync: async ({ text }: { text: string }) => {
      if (!threadId || !_threads[threadId]) {
        throw new Error("Selecione uma conversa para responder.");
      }
      const now = new Date().toISOString();
      const msg: ChatMessage = {
        id: `sent-${threadId}-${_threads[threadId].messages.length}`,
        direction: "outbound",
        body: text,
        created_at: now,
      };
      const t = _threads[threadId];
      _threads = {
        ..._threads,
        [threadId]: {
          ...t,
          messages: [...t.messages, msg],
          lastMessagePreview: text,
          lastMessageAt: now,
          lastDirection: "outbound",
          unreadCount: 0,
        },
      };
      emit();
      return msg;
    },
  }),
  // No useAutoReply — matches the live Meta-DM adapter (no AI toggle for IG DMs).
};
