/**
 * Tests for the ChatWindow organ.
 *
 * Coverage:
 *   1. Thread list — loading skeleton
 *   2. Thread list — error state
 *   3. Thread list — empty state (custom label)
 *   4. Thread list — renders threads, unread badge, "Você:" prefix
 *   5. Right pane — placeholder before a thread is selected
 *   6. Selecting a thread — loading / error / empty / success message states
 *   7. Composer — Send disabled when empty, enabled with text, Enter sends
 *   8. Send failure (thrown Error, e.g. a provider gate) surfaces as an inline banner
 *   9. Auto-reply toggle — rendered + wired when adapter.useAutoReply is provided
 *  10. Auto-reply toggle — absent entirely when adapter omits useAutoReply (e.g. IG DMs)
 *
 * Dual-React gap: resolved in this worktree (NOC-REMEDIATE[harness-vitest-dual-react]
 * RESOLVED 2026-05-29) — full render tests are safe, no hook mocking needed since
 * ChatWindow only calls the fake adapter object passed in per-test.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";

import { ChatWindow } from "./ChatWindow";
import type { ChatWindowAdapter, ChatMessage, ChatThread } from "./ChatWindow";

afterEach(cleanup);

// ─── Fixtures ──────────────────────────────────────────────────────────────

const threadA: ChatThread = {
  id: "t1",
  title: "João Raphael",
  lastMessagePreview: "Olá, tudo bem?",
  lastMessageAt: new Date().toISOString(),
  lastDirection: "inbound",
  unreadCount: 2,
};

const threadB: ChatThread = {
  id: "t2",
  title: "Maria Silva",
  lastMessagePreview: "Confirmado!",
  lastMessageAt: new Date().toISOString(),
  lastDirection: "outbound",
  unreadCount: 0,
};

function makeMessage(id: string, direction: "inbound" | "outbound", body: string): ChatMessage {
  return { id, direction, body, created_at: new Date().toISOString() };
}

function makeAdapter(overrides: Partial<ChatWindowAdapter> = {}): ChatWindowAdapter {
  return {
    useThreads: () => ({ data: [threadA, threadB], isLoading: false, isError: false }),
    useMessages: () => ({ data: [], isLoading: false, isError: false }),
    useSend: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
    ...overrides,
  };
}

// ─── Tests ─────────────────────────────────────────────────────────────────

describe("ChatWindow — thread list states", () => {
  it("shows a loading skeleton while threads load", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useThreads: () => ({ data: [], isLoading: true, isError: false }) })}
      />,
    );
    expect(screen.getByTestId("chat-thread-list-skeleton")).toBeTruthy();
  });

  it("shows an error state when threads fail to load", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useThreads: () => ({ data: [], isLoading: false, isError: true }) })}
      />,
    );
    expect(screen.getByText("Erro ao carregar conversas.")).toBeTruthy();
  });

  it("shows a custom empty label when there are no threads", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useThreads: () => ({ data: [], isLoading: false, isError: false }) })}
        emptyThreadsLabel="Nenhuma conversa por enquanto."
      />,
    );
    expect(screen.getByText("Nenhuma conversa por enquanto.")).toBeTruthy();
  });

  it("renders threads with unread badge and 'Você:' prefix on outbound last message", () => {
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter()} />);
    expect(screen.getByText("João Raphael")).toBeTruthy();
    expect(screen.getByText("Maria Silva")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy(); // unread badge for threadA
    expect(screen.getByText("Você:")).toBeTruthy(); // threadB last_direction=outbound
  });

  it("shows the empty-selection placeholder before any thread is picked", () => {
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter()} emptySelectionLabel="Selecione uma conversa" />);
    expect(screen.getByText("Selecione uma conversa")).toBeTruthy();
  });

  // REGRESSION for the refetch-unmount bug (`KB § PATTERNS/frontend/
  // lying-loading-state.md`). Whatever the adapter's `isLoading` actually
  // tracks, once `data` holds real rows a `true` value must not replace them
  // with the skeleton — a background poll must not blank the thread list.
  it("REGRESSION: keeps rendering threads when isLoading is true but data is already populated (background refetch)", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useThreads: () => ({ data: [threadA, threadB], isLoading: true, isError: false }),
        })}
      />,
    );
    expect(screen.getByText("João Raphael")).toBeTruthy();
    expect(screen.getByText("Maria Silva")).toBeTruthy();
    expect(screen.queryByTestId("chat-thread-list-skeleton")).toBeNull();
  });
});

describe("ChatWindow — thread panel + messages", () => {
  it("shows a loading skeleton while messages load", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useMessages: () => ({ data: [], isLoading: true, isError: false }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.getByTestId("chat-messages-skeleton")).toBeTruthy();
  });

  it("shows an error state when messages fail to load", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useMessages: () => ({ data: [], isLoading: false, isError: true }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.getByText("Erro ao carregar mensagens.")).toBeTruthy();
  });

  it("shows the empty state when the thread has no messages", () => {
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter()} />);
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.getByText("Nenhuma mensagem ainda.")).toBeTruthy();
  });

  it("renders inbound and outbound bubbles", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Bom dia!"), makeMessage("m2", "outbound", "Tudo bem!")],
            isLoading: false,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.getByText("Bom dia!")).toBeTruthy();
    expect(screen.getByText("Tudo bem!")).toBeTruthy();
  });

  // REGRESSION for the refetch-unmount bug — the user-reported symptom:
  // unmounting a populated message list ALSO destroys scroll position, so
  // this matters more here than on a typical list.
  it("REGRESSION: keeps rendering messages when isLoading is true but data is already populated (background refetch)", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Bom dia!")],
            isLoading: true,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.getByText("Bom dia!")).toBeTruthy();
    expect(screen.queryByTestId("chat-messages-skeleton")).toBeNull();
  });
});

describe("ChatWindow — composer", () => {
  it("disables Send when the input is empty and enables it once text is typed", () => {
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter()} />);
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    const sendBtn = screen.getByLabelText("Enviar mensagem") as HTMLButtonElement;
    expect(sendBtn.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "Oi" } });
    expect(sendBtn.disabled).toBe(false);
  });

  it("Enter key triggers send with the trimmed text", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useSend: () => ({ mutateAsync, isPending: false }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    const input = screen.getByLabelText("Mensagem");
    fireEvent.change(input, { target: { value: "Olá" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ text: "Olá" }));
  });

  it("surfaces a thrown send error (e.g. a provider gate) as an inline banner — never fakes success", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("Requer Revisão do app Meta."));
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useSend: () => ({ mutateAsync, isPending: false }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "Olá" } });
    fireEvent.click(screen.getByLabelText("Enviar mensagem"));
    await waitFor(() => expect(screen.getByTestId("chat-send-error")).toBeTruthy());
    expect(screen.getByText("Requer Revisão do app Meta.")).toBeTruthy();
  });
});

describe("ChatWindow — auto-reply toggle", () => {
  it("renders and calls onToggle when the adapter provides useAutoReply", () => {
    const onToggle = vi.fn();
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useAutoReply: () => ({ enabled: false, isPending: false, onToggle }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    const toggle = screen.getByTestId("chat-auto-reply-toggle");
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it("is entirely absent when the adapter omits useAutoReply (e.g. Instagram DMs)", () => {
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter()} />);
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    expect(screen.queryByTestId("chat-auto-reply-toggle")).toBeNull();
  });
});

// ─── Read-state + pagination seams (added 2026-08 with the realtime inbox) ──
describe("ChatWindow — read-state seam", () => {
  it("marks a thread read exactly once when it is opened", async () => {
    const markRead = vi.fn();
    const adapter = makeAdapter({ useReadState: () => ({ markRead }) });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    await waitFor(() => expect(markRead).toHaveBeenCalledWith("t1"));
    // 🔴 The WhatsApp adapter's markRead marks the chat read on the user's REAL
    // phone. Firing it more than once per open would be a stream of side
    // effects on a live account, so the count is the assertion, not the call.
    expect(markRead).toHaveBeenCalledTimes(1);
  });

  it("marks the newly-opened thread read when switching threads", async () => {
    const markRead = vi.fn();
    const adapter = makeAdapter({ useReadState: () => ({ markRead }) });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));
    await waitFor(() => expect(markRead).toHaveBeenCalledWith("t1"));

    fireEvent.click(screen.getByText("Maria Silva"));
    await waitFor(() => expect(markRead).toHaveBeenCalledWith("t2"));
    expect(markRead).toHaveBeenCalledTimes(2);
  });

  it("never marks anything read when the adapter omits useReadState", async () => {
    // Providers without read receipts (e.g. IG DMs) must render unchanged.
    const adapter = makeAdapter({
      useMessages: () => ({ data: [makeMessage("m1", "inbound", "oi")], isLoading: false, isError: false }),
    });
    expect(adapter.useReadState).toBeUndefined();

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));
    await waitFor(() => expect(screen.getByTestId("chat-messages")).toBeInTheDocument());
  });
});

describe("ChatWindow — load-more seam", () => {
  it("renders the load-older control and wires it when hasMore", async () => {
    const loadMore = vi.fn();
    const adapter = makeAdapter({
      useLoadMore: () => ({ hasMore: true, isLoadingMore: false, loadMore }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const btn = await screen.findByTestId("chat-load-more");
    fireEvent.click(btn);
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it("hides the control once there is nothing older", async () => {
    const adapter = makeAdapter({
      useMessages: () => ({ data: [makeMessage("m1", "inbound", "oi")], isLoading: false, isError: false }),
      useLoadMore: () => ({ hasMore: false, isLoadingMore: false, loadMore: vi.fn() }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    await waitFor(() => expect(screen.getByTestId("chat-messages")).toBeInTheDocument());
    expect(screen.queryByTestId("chat-load-more")).not.toBeInTheDocument();
  });

  it("omitting useLoadMore leaves the thread with no pagination affordance", async () => {
    const adapter = makeAdapter({
      useMessages: () => ({ data: [makeMessage("m1", "inbound", "oi")], isLoading: false, isError: false }),
    });
    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    await waitFor(() => expect(screen.getByTestId("chat-messages")).toBeInTheDocument());
    expect(screen.queryByTestId("chat-load-more")).not.toBeInTheDocument();
  });
});

describe("ChatWindow — empty thread with older history", () => {
  it("still offers load-older when the newest page is empty but more exists", async () => {
    // Regression pin: this combination previously fell through to the empty
    // state, stranding the user with no way to reach messages that do exist.
    const loadMore = vi.fn();
    const adapter = makeAdapter({
      useMessages: () => ({ data: [], isLoading: false, isError: false }),
      useLoadMore: () => ({ hasMore: true, isLoadingMore: false, loadMore }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const btn = await screen.findByTestId("chat-load-more");
    fireEvent.click(btn);
    expect(loadMore).toHaveBeenCalledTimes(1);
  });
});
