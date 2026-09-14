/**
 * useJuliaChat.ts hook tests — contract §E.2 (conversations/messages),
 * §E.3 (SSE events → messages cache / blocks / streaming bubble, revised
 * 2026-09-14), §E.7.
 *
 * Stubs `@/lib/api` (HTTP boundary), `@noctusai/seed/infra` (getAuthToken),
 * and `@noctusai/lib`'s `useRealtimeStream` (captures `onEvent` + `events`
 * so each SSE event can be dispatched directly, exactly like
 * `WhatsAppChatWindow.test.tsx`'s "no real HTTP/SSE" convention).
 *
 * The `message.new` / `message.updated` / `tool.*` / `approval.*` tests
 * REPLAY the canonical published stream at
 * `products/agents/contract-fixtures/escrita-turn.events.json` — never a
 * hand-written payload. That fixture is the one both the backend route
 * tests and this hook assert against (contract §E.3 "Canonical stream");
 * hand-writing an `approval.requested` payload here is exactly how the
 * earlier, broken Approve button (missing `id`) shipped green.
 */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import escritaTurnFixture from "../../../../contract-fixtures/escrita-turn.events.json";

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

interface FixtureEvent {
  event: string;
  payload: Record<string, unknown>;
}

const FIXTURE_EVENTS = (escritaTurnFixture as { events: FixtureEvent[] }).events;

/** Index of the first `approval.requested` event, and of the
 * `message.updated` that immediately follows it (contract §E.3: "the
 * granular event first, then `message.updated`"). */
const APPROVAL_REQUESTED_IDX = FIXTURE_EVENTS.findIndex((e) => e.event === "approval.requested");
const APPROVAL_ID = String(FIXTURE_EVENTS[APPROVAL_REQUESTED_IDX].payload.id);

/**
 * The persisted-row equivalent of replaying every `message.new` /
 * `message.updated` in the fixture (last-write-wins per id, in first-seen
 * order) — i.e. what a real `GET .../messages` returns once every event has
 * landed in the database. Used to stub the refetch contract §E.3 mandates
 * when `session.status` leaves `"pensando"`, so that refetch reconciles to
 * the SAME state the SSE stream already built, exactly as the real backend
 * would (never to a stale/empty response a real API would not send).
 */
function finalMessagesFromFixture(events: FixtureEvent[]) {
  const byId = new Map<string, Record<string, unknown>>();
  const order: string[] = [];
  for (const e of events) {
    if (e.event === "message.new" || e.event === "message.updated") {
      const msg = e.payload;
      const id = String(msg.id);
      if (!byId.has(id)) order.push(id);
      byId.set(id, msg);
    }
  }
  return order.map((id) => byId.get(id));
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

// ─── Messages + realtime (contract §E.3, revised 2026-09-14) ───────────────

async function renderMessages(conversationId = "00000000-0000-4000-8000-0000000000c1") {
  mockGet.mockResolvedValue({ items: [], total: 0 });
  const { useJuliaMessagesAdapter } = await import("@/hooks/useJuliaChat");
  const qc = newClient();
  const { result } = renderHook(() => useJuliaMessagesAdapter(conversationId), {
    wrapper: wrapper(qc),
  });
  // Wait for the initial GET to settle before replaying any SSE event —
  // otherwise an event dispatched while `query.data` is still `undefined`
  // is silently dropped (`setQueryData`'s updater returning its own
  // `undefined` `prev` is a no-op), exactly the race the real ChatWindow
  // avoids by mounting the subscription only once a thread is open.
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  const [, options] = mockUseRealtimeStream.mock.calls[mockUseRealtimeStream.mock.calls.length - 1];
  return { result, options, qc };
}

/** Dispatch fixture events `[0, uptoExclusive)` through the captured `onEvent`. */
function replay(options: { onEvent: (evt: FixtureEvent) => void }, uptoExclusive: number) {
  for (let i = 0; i < uptoExclusive; i++) {
    act(() => {
      options.onEvent(FIXTURE_EVENTS[i]);
    });
  }
}

describe("useJuliaMessagesAdapter — REST + subscription wiring", () => {
  it("GETs the message list", async () => {
    await renderMessages();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/conversations/00000000-0000-4000-8000-0000000000c1/messages",
    );
  });

  it("subscribes to /api/conversations/{id}/stream with EVERY §E.3 event name, including message.updated", async () => {
    const { options } = await renderMessages();
    expect(mockUseRealtimeStream).toHaveBeenCalledWith(
      "/api/conversations/00000000-0000-4000-8000-0000000000c1/stream",
      expect.objectContaining({ getAuthToken: expect.any(Function) }),
    );
    const expected = [
      "message.new",
      "message.updated",
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

  it("replaying the full canonical fixture leaves the cache with the user message and both assistant messages, blocks in their final state, and no __live__ bubble", async () => {
    const { result, options } = await renderMessages();

    // The final `session.status: "ociosa"` triggers the contract §E.3
    // "refetch once" — stub it to what the real backend would now return
    // (every event already persisted), so the reconciliation lands on the
    // SAME state the SSE stream built, not a stale empty response.
    const finalItems = finalMessagesFromFixture(FIXTURE_EVENTS);
    mockGet.mockResolvedValue({ items: finalItems, total: finalItems.length });

    replay(options, FIXTURE_EVENTS.length);

    await waitFor(() => expect(result.current.data).toHaveLength(3));

    const [userMsg, assistantA, assistantB] = result.current.data;
    expect(userMsg).toMatchObject({ id: "00000000-0000-4000-8000-0000000000a1", direction: "outbound" });
    expect(assistantA).toMatchObject({ id: "00000000-0000-4000-8000-0000000000a2", direction: "inbound" });
    expect(assistantA.blocks).toEqual([
      { kind: "tool", toolUseId: "toolu_fixture_01", name: "mcp__academia__kb_escrever", status: "ok", resumo: "Editar KB: exemplo" },
      {
        kind: "approval",
        approvalId: APPROVAL_ID,
        resumo: "Editar KB: exemplo",
        diff: { antes: "Texto antigo.", depois: "Texto novo." },
        decision: "aprovada",
      },
    ]);
    expect(assistantB).toMatchObject({ id: "00000000-0000-4000-8000-0000000000a3", direction: "inbound" });
    expect(result.current.data.some((m: any) => m.id === "__live__")).toBe(false);
  });

  it("replaying up to the first approval.requested + its message.updated produces a pendente approval block whose approvalId matches the fixture, and decide() posts to that id", async () => {
    const { result, options } = await renderMessages();

    // The event immediately after approval.requested is its message.updated
    // (contract §E.3: "the granular event first, then message.updated").
    replay(options, APPROVAL_REQUESTED_IDX + 2);

    await waitFor(() => {
      const assistantA = result.current.data.find((m: any) => m.id === "00000000-0000-4000-8000-0000000000a2");
      expect(assistantA?.blocks).toContainEqual(
        expect.objectContaining({ kind: "approval", approvalId: APPROVAL_ID, decision: "pendente" }),
      );
    });

    const { useJuliaApprovalActionAdapter } = await import("@/hooks/useJuliaChat");
    mockPost.mockResolvedValue({ id: APPROVAL_ID, decision: "aprovada" });
    const qc2 = newClient();
    const { result: actionResult } = renderHook(() => useJuliaApprovalActionAdapter(), { wrapper: wrapper(qc2) });
    await actionResult.current.decide(APPROVAL_ID, true);

    expect(mockPost).toHaveBeenCalledWith(`/api/approvals/${APPROVAL_ID}/decision`, { aprovada: true });
  });

  it("message.delta shows a pending live bubble that clears on the assistant message.new", async () => {
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

  it("a message.new for the USER's own message does not clear an existing live bubble", async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({ event: "message.delta", payload: { message_temp_id: "tmp1", texto_parcial: "Ainda pensando" } });
    });
    await waitFor(() => {
      expect(result.current.data.find((m: any) => m.id === "__live__")).toMatchObject({ pending: true });
    });

    act(() => {
      options.onEvent({
        event: "message.new",
        payload: { id: "mu1", conversation_id: "c1", role: "user", texto: "outra pergunta", blocks: [], token_usage: null, created_at: "t", updated_at: "t" },
      });
    });
    await waitFor(() => {
      expect(result.current.data.find((m: any) => m.id === "__live__")).toMatchObject({ pending: true });
    });
  });

  it('tool.started / tool.finished no longer build blocks on the live bubble — they are no-ops', async () => {
    const { result, options } = await renderMessages();

    act(() => {
      options.onEvent({ event: "session.status", payload: { status: "pensando" } });
    });
    act(() => {
      options.onEvent({
        event: "tool.started",
        payload: { tool_use_id: "t1", tool_name: "mcp__academia__kb_buscar", classe: "leitura", resumo: "buscando..." },
      });
    });
    act(() => {
      options.onEvent({ event: "tool.finished", payload: { tool_use_id: "t1", tool_name: "mcp__academia__kb_buscar", resultado: "ok" } });
    });

    const live: any = result.current.data.find((m: any) => m.id === "__live__");
    expect(live).toBeDefined();
    expect(live.blocks).toBeUndefined();
  });

  it('session.status "pensando" shows the live bubble; leaving it clears the bubble and invalidates the messages query exactly once', async () => {
    const { result, options, qc } = await renderMessages();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    act(() => {
      options.onEvent({ event: "session.status", payload: { status: "pensando" } });
    });
    await waitFor(() => {
      const live: any = result.current.data.find((m: any) => m.id === "__live__");
      expect(live).toMatchObject({ pending: true, body: "Julia está pensando…" });
    });

    invalidateSpy.mockClear();
    act(() => {
      options.onEvent({ event: "session.status", payload: { status: "ociosa", sdk_session_id: "sess-1" } });
    });
    await waitFor(() => {
      expect(result.current.data.some((m: any) => m.id === "__live__")).toBe(false);
    });

    const messagesInvalidations = invalidateSpy.mock.calls.filter(([arg]) =>
      JSON.stringify((arg as any)?.queryKey).includes("messages"),
    );
    expect(messagesInvalidations).toHaveLength(1);
  });

  it("approval.requested and approval.resolved each invalidate the approvals list query", async () => {
    const { options, qc } = await renderMessages();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    act(() => {
      options.onEvent(FIXTURE_EVENTS[APPROVAL_REQUESTED_IDX]);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["agents", "approvals"] });

    invalidateSpy.mockClear();
    const resolvedEvt = FIXTURE_EVENTS.find((e) => e.event === "approval.resolved")!;
    act(() => {
      options.onEvent(resolvedEvt);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["agents", "approvals"] });
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
    mockPost.mockRejectedValue(
      new ApiError(409, "Já existe um turno em andamento.", {
        detail: "Já existe um turno em andamento.",
        code: "turn_in_progress",
      }),
    );
    const { useJuliaSendAdapter } = await import("@/hooks/useJuliaChat");
    const qc = newClient();
    const { result } = renderHook(() => useJuliaSendAdapter("c1"), { wrapper: wrapper(qc) });

    await expect(result.current.mutateAsync({ text: "Oi" })).rejects.toThrow(
      "Julia ainda está respondendo a mensagem anterior.",
    );
  });

  it("maps a 409 agent_off rejection to the PT-BR composer message", async () => {
    const { ApiError } = await import("@/lib/errors");
    mockPost.mockRejectedValue(
      new ApiError(409, "O agente Julia está desligado.", {
        detail: "O agente Julia está desligado.",
        code: "agent_off",
      }),
    );
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
