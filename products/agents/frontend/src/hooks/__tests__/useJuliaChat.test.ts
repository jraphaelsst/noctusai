/**
 * useJuliaChat.ts hook tests — contract §E.2 (conversations/messages),
 * §E.3 (SSE events → ChatWindow blocks/pending), §E.7.
 *
 * Stubs `@/lib/api` (HTTP boundary), `@noctusai/seed/infra` (getAuthToken),
 * and `@noctusai/lib`'s `useRealtimeStream` (captures `onEvent` + `events`
 * so each SSE event can be dispatched directly, exactly like
 * `WhatsAppChatWindow.test.tsx`'s "no real HTTP/SSE" convention).
 */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => ({
  getAuthToken: vi.fn().mockResolvedValue("token-123"),
}));

const mockUseRealtimeStream = vi.fn();
// Real module preserved (ApiError etc. — `@/lib/errors` imports `ApiError`
// from here too) — only `useRealtimeStream` is stubbed, so SSE never opens
// a real `fetch` under jsdom.
vi.mock("@noctusai/lib", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@noctusai/lib")>();
  return {
    ...actual,
    useRealtimeStream: (url: string | null, options: any) => mockUseRealtimeStream(url, options),
  };
});

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseRealtimeStream.mockReturnValue({ status: "open", lastEventId: null });
});

// ─── Threads ────────────────────────────────────────────────────────────────

describe("useThreads", () => {
  it("GETs /api/conversations and maps to ChatThread, newest first", async () => {
    mockGet.mockResolvedValue({
      items: [
        { id: "c1", agent_id: "a1", owner_user_id: "u1", titulo: "Velha", sdk_session_id: null, status: "ativa", last_message_at: "2026-09-01T10:00:00Z", created_at: "2026-09-01T09:00:00Z", updated_at: "2026-09-01T10:00:00Z" },
        { id: "c2", agent_id: "a1", owner_user_id: "u1", titulo: null, sdk_session_id: null, status: "ativa", last_message_at: "2026-09-02T10:00:00Z", created_at: "2026-09-02T09:00:00Z", updated_at: "2026-09-02T10:00:00Z" },
      ],
      total: 2,
    });
    const { useThreads } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useThreads(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/conversations");
    expect(result.current.data.map((t) => t.id)).toEqual(["c2", "c1"]); // newest first
    expect(result.current.data[0].title).toBe("Nova conversa"); // null titulo fallback
  });
});

describe("useCreateConversation", () => {
  it("POSTs /api/conversations with {titulo}", async () => {
    mockPost.mockResolvedValue({ id: "c3", agent_id: "a1", owner_user_id: "u1", titulo: "Oi", sdk_session_id: null, status: "ativa", last_message_at: null, created_at: "t", updated_at: "t" });
    const { useCreateConversation } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useCreateConversation(), { wrapper: wrapper(qc) });

    result.current.mutate({ titulo: "Oi" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/conversations", { titulo: "Oi" });
  });
});

// ─── Messages + realtime (contract §E.3) ───────────────────────────────────

const RAW_MESSAGE = {
  id: "m1",
  conversation_id: "c1",
  role: "user",
  texto: "Oi Julia",
  blocks: [],
  token_usage: null,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

async function renderMessages(conversationId = "c1") {
  mockGet.mockResolvedValue({ items: [RAW_MESSAGE], total: 1 });
  const { useJuliaMessagesAdapter } = await import("@/hooks/useJuliaChat");
  const qc = newClient();
  const { result } = renderHook(() => useJuliaMessagesAdapter(conversationId), {
    wrapper: wrapper(qc),
  });
  await waitFor(() => expect(result.current.data.length).toBeGreaterThan(0));
  const [, options] = mockUseRealtimeStream.mock.calls[mockUseRealtimeStream.mock.calls.length - 1];
  return { result, options, qc };
}

describe("useJuliaMessagesAdapter — REST + subscription wiring", () => {
  it("GETs the message list and maps role → direction", async () => {
    const { result } = await renderMessages();
    expect(mockGet).toHaveBeenCalledWith("/api/conversations/c1/messages");
    expect(result.current.data).toEqual([
      { id: "m1", direction: "outbound", body: "Oi Julia", created_at: "2026-09-01T10:00:00Z", blocks: undefined },
    ]);
  });

  it("subscribes to /api/conversations/{id}/stream with EVERY §E.3 event name", async () => {
    const { options } = await renderMessages();
    expect(mockUseRealtimeStream).toHaveBeenCalledWith(
      "/api/conversations/c1/stream",
      expect.objectContaining({ getAuthToken: expect.any(Function) }),
    );
    const expected = [
      "message.new",
      "message.delta",
      "tool.started",
      "tool.finished",
      "approval.requested",
      "approval.resolved",
      "session.status",
      "conversation.upsert",
    ];
    for (const name of expected) {
      expect(options.events).toContain(name);
    }
  });

  it("message.new appends a new assistant message", async () => {
    const { result, options } = await renderMessages();
    act(() => {
      options.onEvent({
        event: "message.new",
        payload: {
          id: "m2",
          conversation_id: "c1",
          role: "assistant",
          texto: "Olá! Como posso ajudar?",
          blocks: [],
          token_usage: null,
          created_at: "2026-09-01T10:00:05Z",
          updated_at: "2026-09-01T10:00:05Z",
        },
      });
    });
    await waitFor(() => expect(result.current.data).toHaveLength(2));
    expect(result.current.data[1]).toMatchObject({ id: "m2", direction: "inbound", body: "Olá! Como posso ajudar?" });
  });

  it("message.delta shows a pending live bubble that a later message.new replaces", async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({ event: "message.delta", payload: { message_temp_id: "tmp1", texto_parcial: "Deixa eu ver..." } });
    });
    await waitFor(() => {
      const live = result.current.data.find((m: any) => m.id === "__live__");
      expect(live).toMatchObject({ pending: true, body: "Deixa eu ver..." });
    });

    act(() => {
      options.onEvent({
        event: "message.new",
        payload: { id: "m2", conversation_id: "c1", role: "assistant", texto: "Pronto.", blocks: [], token_usage: null, created_at: "t", updated_at: "t" },
      });
    });
    await waitFor(() => {
      expect(result.current.data.some((m: any) => m.id === "__live__")).toBe(false);
      expect(result.current.data.some((m: any) => m.id === "m2")).toBe(true);
    });
  });

  it("tool.started then tool.finished produce ONE tool block keyed by tool_use_id", async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({
        event: "tool.started",
        payload: { tool_use_id: "t1", tool_name: "mcp__academia__kb_buscar", classe: "leitura", resumo: "buscando..." },
      });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live.blocks).toEqual([
        { kind: "tool", toolUseId: "t1", name: "mcp__academia__kb_buscar", status: "running", resumo: "buscando..." },
      ]);
    });

    act(() => {
      options.onEvent({ event: "tool.finished", payload: { tool_use_id: "t1", tool_name: "mcp__academia__kb_buscar", resultado: "ok" } });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live.blocks).toHaveLength(1);
      expect(live.blocks[0]).toMatchObject({ toolUseId: "t1", status: "ok" });
    });
  });

  it("approval.requested then approval.resolved produce an approval block with the decision updated", async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({
        event: "approval.requested",
        payload: { id: "ap1", resumo: "Editar KB dominio-x", diff: { antes: "old", depois: "new" } },
      });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live.blocks[0]).toMatchObject({ kind: "approval", approvalId: "ap1", decision: "pendente" });
    });

    act(() => {
      options.onEvent({ event: "approval.resolved", payload: { approval_id: "ap1", decision: "aprovada", decided_by: "u1" } });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live.blocks[0]).toMatchObject({ approvalId: "ap1", decision: "aprovada" });
    });
  });

  it('session.status "pensando" shows the live bubble; a non-pensando status clears it', async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({ event: "session.status", payload: { status: "pensando" } });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live).toMatchObject({ pending: true, body: "Julia está pensando…" });
    });

    act(() => {
      options.onEvent({ event: "session.status", payload: { status: "ociosa" } });
    });
    await waitFor(() => {
      expect(result.current.data.some((m: any) => m.id === "__live__")).toBe(false);
    });
  });

  it("conversation.upsert patches the thread-list cache", async () => {
    const { qc, options } = await renderMessages();
    qc.setQueryData(["agents", "julia", "conversations"], {
      items: [{ id: "c1", agent_id: "a1", owner_user_id: "u1", titulo: "Old", sdk_session_id: null, status: "ativa", last_message_at: null, created_at: "t", updated_at: "t" }],
      total: 1,
    });

    act(() => {
      options.onEvent({
        event: "conversation.upsert",
        payload: { id: "c1", agent_id: "a1", owner_user_id: "u1", titulo: "Nova conversa gerada", sdk_session_id: "sdk1", status: "ativa", last_message_at: "2026-09-01T10:00:05Z", created_at: "t", updated_at: "t2" },
      });
    });

    await waitFor(() => {
      const cached: any = qc.getQueryData(["agents", "julia", "conversations"]);
      expect(cached.items[0].titulo).toBe("Nova conversa gerada");
    });
  });
});

// ─── Send (contract §E.2, error mapping) ───────────────────────────────────

describe("useJuliaSendAdapter", () => {
  it("POSTs {texto} to .../messages", async () => {
    mockPost.mockResolvedValue({ mensagem: RAW_MESSAGE, status: "processando" });
    const { useJuliaSendAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaSendAdapter("c1"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ text: "Oi Julia" });
    expect(mockPost).toHaveBeenCalledWith("/api/conversations/c1/messages", { texto: "Oi Julia" });
  });

  it("maps a 409 turn_in_progress rejection to the PT-BR composer message", async () => {
    const { ApiError } = await import("@/lib/errors");
    mockPost.mockRejectedValue(new ApiError(409, "Já existe um turno em andamento."));
    const { useJuliaSendAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaSendAdapter("c1"), { wrapper: wrapper(qc) });

    await expect(result.current.mutateAsync({ text: "Oi" })).rejects.toThrow(
      "Julia ainda está respondendo a mensagem anterior.",
    );
  });

  it("maps a 409 agent_off rejection to the PT-BR composer message", async () => {
    const { ApiError } = await import("@/lib/errors");
    mockPost.mockRejectedValue(new ApiError(409, "O agente Julia está desligado."));
    const { useJuliaSendAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaSendAdapter("c1"), { wrapper: wrapper(qc) });

    await expect(result.current.mutateAsync({ text: "Oi" })).rejects.toThrow(
      "Julia está desligada — um administrador pode ligá-la em Agentes.",
    );
  });
});

// ─── Approval action (ChatWindow seam, contract §E.7) ──────────────────────

describe("useJuliaApprovalActionAdapter", () => {
  it("decide() POSTs {aprovada} to /api/approvals/{id}/decision", async () => {
    mockPost.mockResolvedValue({ id: "ap1", decision: "aprovada" });
    const { useJuliaApprovalActionAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaApprovalActionAdapter(), { wrapper: wrapper(qc) });

    await result.current.decide("ap1", true);
    expect(mockPost).toHaveBeenCalledWith("/api/approvals/ap1/decision", { aprovada: true });
  });

  it("already_decided rejects with the mapped message", async () => {
    const { ApiError } = await import("@/lib/errors");
    mockPost.mockRejectedValue(new ApiError(409, "Esta aprovação já foi decidida."));
    const { useJuliaApprovalActionAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaApprovalActionAdapter(), { wrapper: wrapper(qc) });

    await expect(result.current.decide("ap1", true)).rejects.toThrow(
      "Esta aprovação já foi decidida.",
    );
  });
});
