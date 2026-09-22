/**
 * ChatTab.tsx tests — Agent Studio CONTRACT.md §G "Conversar". Stubs
 * `useStudioChat.ts` (adapter builder + create-conversation mutation) and
 * `useClients.ts` (client selector — the ONE client hooks module now that
 * `useClientsKe.ts` was collapsed into it); the seed `<ChatWindow>` organ
 * itself renders for real (its own states are covered by its colocated test).
 */
import React from "react";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockBuildStudioChatAdapter = vi.fn();
const mockUseCreateStudioConversation = vi.fn();
const mockUseClients = vi.fn();

vi.mock("@/hooks/studio/useStudioChat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/studio/useStudioChat")>();
  return {
    ...actual,
    buildStudioChatAdapter: (key: string) => mockBuildStudioChatAdapter(key),
    useCreateStudioConversation: () => mockUseCreateStudioConversation(),
  };
});
vi.mock("@/hooks/studio/useClients", () => ({ useClients: () => mockUseClients() }));

const NOOP_ADAPTER = {
  useThreads: () => ({ data: [], isLoading: false, isError: false }),
  useMessages: () => ({ data: [], isLoading: false, isError: false }),
  useSend: () => ({ mutateAsync: vi.fn(), isPending: false }),
};

beforeEach(() => {
  vi.clearAllMocks();
  mockBuildStudioChatAdapter.mockReturnValue(NOOP_ADAPTER);
  mockUseCreateStudioConversation.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({ id: "c1" }) });
  mockUseClients.mockReturnValue({ data: [], showSkeleton: false, isError: false, error: null });
});

afterEach(() => cleanup());

async function renderTab() {
  const ChatTab = (await import("@/pages/studio/tabs/ChatTab")).default;
  render(React.createElement(ChatTab, { agentKey: "isaia" }));
}

describe("ChatTab", () => {
  it("renders the ChatWindow organ scoped to the agent key, with the 'Nova conversa' action", async () => {
    await renderTab();
    expect(screen.getByTestId("chat-window")).toBeTruthy();
    expect(screen.getByTestId("studio-chat-new-conversation")).toBeTruthy();
    expect(mockBuildStudioChatAdapter).toHaveBeenCalledWith("isaia");
  });

  it("hides the client selector when the agent has no active clients", async () => {
    await renderTab();
    expect(screen.queryByTestId("chat-tab-client-select")).toBeNull();
  });

  it("shows a client selector and passes the selected client_id on conversation creation", async () => {
    mockUseClients.mockReturnValue({
      data: [{ id: "cl1", slug: "cliente-a", nome: "Cliente A", resumo: "", ativo: true, total_entradas: 0 }],
      showSkeleton: false,
      isError: false,
      error: null,
    });
    await renderTab();

    const select = screen.getByTestId("chat-tab-client-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "cl1" } });
    fireEvent.click(screen.getByTestId("studio-chat-new-conversation"));

    await waitFor(() => expect(mockUseCreateStudioConversation().mutateAsync).toHaveBeenCalled());
    expect(mockUseCreateStudioConversation().mutateAsync).toHaveBeenCalledWith({ clientId: "cl1" });
  });
});
