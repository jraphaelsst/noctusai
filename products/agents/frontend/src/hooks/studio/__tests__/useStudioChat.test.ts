/**
 * useStudioChat.ts hook tests — Agent Studio CONTRACT.md §D6, §G "Conversar".
 * Mirrors `useJuliaChat.test.ts`'s mocking convention (`@/lib/api`,
 * `@noctusai/seed/infra`, `useRealtimeStream` captured, no real HTTP/SSE).
 */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => ({
  getAuthToken: vi.fn().mockResolvedValue("token-123"),
}));

const mockUseRealtimeStream = vi.fn();
vi.mock("@noctusai/lib", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@noctusai/lib")>();
  return {
    ...actual,
    useRealtimeStream: (url: string | null, options: any) => mockUseRealtimeStream(url, options),
  };
});

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseRealtimeStream.mockReturnValue({ status: "open", lastEventId: null });
});
afterEach(() => vi.clearAllMocks());

const CONVERSATION = {
  id: "c1",
  agent_id: "a1",
  agent_key: "isaia",
  owner_user_id: "u1",
  titulo: null,
  sdk_session_id: null,
  status: "ativa",
  version_id: "v1",
  client_id: null,
  last_message_at: "2026-09-21T10:00:00Z",
  created_at: "2026-09-21T09:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
};

describe("useStudioThreads", () => {
  it("GETs /api/conversations filtered by agent_key", async () => {
    mockGet.mockResolvedValue({ items: [CONVERSATION], total: 1 });
    const { useStudioThreads } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    const { result } = renderHook(() => useStudioThreads("isaia"), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/conversations", { agent_key: "isaia" });
    expect(result.current.data[0].title).toBe("Nova conversa");
  });
});

describe("useCreateStudioConversation", () => {
  it("POSTs {agent_key, client_id} on creation", async () => {
    mockPost.mockResolvedValue({ ...CONVERSATION, id: "c2" });
    const { useCreateStudioConversation } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    const { result } = renderHook(() => useCreateStudioConversation("isaia"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ clientId: "cl1" });
    expect(mockPost).toHaveBeenCalledWith("/api/conversations", { agent_key: "isaia", client_id: "cl1" });
  });

  it("omits client_id when no client is selected", async () => {
    mockPost.mockResolvedValue(CONVERSATION);
    const { useCreateStudioConversation } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    const { result } = renderHook(() => useCreateStudioConversation("isaia"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync(undefined);
    expect(mockPost).toHaveBeenCalledWith("/api/conversations", { agent_key: "isaia", client_id: undefined });
  });
});

describe("useStudioMessagesAdapter — versão/hash link block", () => {
  it("attaches a link block reading 'versão N · prompt sha256:…' to assistant messages, resolved off the version's versao", async () => {
    // Threads list (feeds `useConversationFromCache` -> conversation.version_id)
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/conversations") return Promise.resolve({ items: [CONVERSATION], total: 1 });
      if (path === "/api/conversations/c1/messages") {
        return Promise.resolve({
          items: [
            { id: "m1", conversation_id: "c1", role: "assistant", texto: "Aqui está.", blocks: [], version_id: "v1", compiled_hash: "sha256:1a2b3c4d5e6f", token_usage: null, created_at: "t", updated_at: "t" },
          ],
          total: 1,
        });
      }
      if (path === "/api/studio/agents/isaia/versions/v1") return Promise.resolve({ versao: 3 });
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });

    const { useStudioThreads, useStudioMessagesAdapter } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    // Threads must be in the cache for useConversationFromCache to resolve.
    renderHook(() => useStudioThreads("isaia"), { wrapper: wrapper(qc) });
    const { result } = renderHook(() => useStudioMessagesAdapter("isaia", "c1"), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await waitFor(() => expect(result.current.data[0]?.blocks?.length).toBeGreaterThan(0));

    const linkBlock = result.current.data[0].blocks?.[0] as { kind: string; label: string; href: string };
    expect(linkBlock.kind).toBe("link");
    expect(linkBlock.label).toBe("versão 3 · prompt sha256:1a2b3c4d…");
    // encodeURIComponent-escaped (the ":" in "sha256:..." is not a URL-safe
    // path-segment char) — see useStudioChat.ts's toChatMessage for why.
    expect(linkBlock.href).toBe("/studio/prompts/sha256%3A1a2b3c4d5e6f");
  });

  it("mounts the realtime stream naming every STUDIO_STREAM_EVENTS entry", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/conversations") return Promise.resolve({ items: [], total: 0 });
      if (path === "/api/conversations/c1/messages") return Promise.resolve({ items: [], total: 0 });
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    const { useStudioMessagesAdapter, STUDIO_STREAM_EVENTS } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    const { result } = renderHook(() => useStudioMessagesAdapter("isaia", "c1"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockUseRealtimeStream).toHaveBeenCalledWith(
      "/api/conversations/c1/stream",
      expect.objectContaining({ events: STUDIO_STREAM_EVENTS }),
    );
    // No approval seam for studio agents (no write tools, §E.3).
    expect(STUDIO_STREAM_EVENTS).not.toContain("approval.requested");
  });

  it("message.delta drives a pending streaming bubble, cleared by the next message.new", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/conversations") return Promise.resolve({ items: [], total: 0 });
      if (path === "/api/conversations/c1/messages") return Promise.resolve({ items: [], total: 0 });
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    const { useStudioMessagesAdapter } = await import("@/hooks/studio/useStudioChat");
    const qc = newClient();
    const { result } = renderHook(() => useStudioMessagesAdapter("isaia", "c1"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const [, options] = mockUseRealtimeStream.mock.calls[mockUseRealtimeStream.mock.calls.length - 1];
    act(() => options.onEvent({ event: "session.status", payload: { status: "pensando" } }));
    act(() => options.onEvent({ event: "message.delta", payload: { texto_parcial: "Escrevendo" } }));

    const lastMessage = result.current.data[result.current.data.length - 1];
    expect(lastMessage?.pending).toBe(true);
    expect(lastMessage?.body).toBe("Escrevendo");

    act(() =>
      options.onEvent({
        event: "message.new",
        payload: { id: "m2", conversation_id: "c1", role: "assistant", texto: "Pronto.", blocks: [], version_id: null, compiled_hash: null, token_usage: null, created_at: "t", updated_at: "t" },
      }),
    );
    expect(result.current.data.some((m: any) => m.id === "__live__")).toBe(false);
  });
});
