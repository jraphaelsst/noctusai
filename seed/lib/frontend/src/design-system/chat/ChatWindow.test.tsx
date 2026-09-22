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
import { useState } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";

import { ChatWindow } from "./ChatWindow";
import type { ChatBlock, ChatWindowAdapter, ChatMessage, ChatThread } from "./ChatWindow";

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

function makeMessage(
  id: string,
  direction: "inbound" | "outbound",
  body: string,
  extra: Partial<ChatMessage> = {},
): ChatMessage {
  return { id, direction, body, created_at: new Date().toISOString(), ...extra };
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

  // Contract: `ChatSendResult.retryAfterSeconds` (optional, REACTIVE — the
  // adapter owns the countdown state/timer; ChatWindow only reads it each
  // render). Ticking itself is tested where it lives, in the Julia adapter
  // (`useJuliaChat.test.ts`, fake timers) — here it's the seed contract:
  // disable the composer while positive, show a live suffix, re-enable at 0.
  it("disables the composer and shows a live countdown while the adapter reports retryAfterSeconds > 0, and re-enables at 0", async () => {
    const setCooldownRef: { current: (n: number | null) => void } = { current: () => {} };
    function useSend() {
      const [retryAfterSeconds, setRetryAfterSeconds] = useState<number | null>(null);
      setCooldownRef.current = setRetryAfterSeconds;
      return {
        mutateAsync: async () => {
          setRetryAfterSeconds(5);
          throw new Error("A Julia está atendendo o número máximo de conversas agora.");
        },
        isPending: false,
        retryAfterSeconds,
      };
    }
    render(<ChatWindow scopeId="scope-1" adapter={makeAdapter({ useSend })} />);
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "Oi" } });
    fireEvent.click(screen.getByLabelText("Enviar mensagem"));

    await waitFor(() => expect(screen.getByTestId("chat-send-error")).toBeTruthy());
    expect(screen.getByTestId("chat-send-retry-countdown").textContent).toContain("5s");
    expect((screen.getByLabelText("Enviar mensagem") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Mensagem") as HTMLInputElement).disabled).toBe(true);

    act(() => setCooldownRef.current(0));

    expect(screen.queryByTestId("chat-send-retry-countdown")).toBeNull();
    expect((screen.getByLabelText("Mensagem") as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByLabelText("Enviar mensagem") as HTMLButtonElement).disabled).toBe(true); // empty input
  });

  it("an adapter that never sets retryAfterSeconds behaves exactly as before (WhatsApp/IG — no countdown seam)", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("Falha ao enviar."));
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({ useSend: () => ({ mutateAsync, isPending: false }) })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "Oi" } });
    fireEvent.click(screen.getByLabelText("Enviar mensagem"));

    await waitFor(() => expect(screen.getByTestId("chat-send-error")).toBeTruthy());
    expect(screen.queryByTestId("chat-send-retry-countdown")).toBeNull();
    expect((screen.getByLabelText("Mensagem") as HTMLInputElement).disabled).toBe(false);
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

// ─── SEED-2 additive seams (contract §E.7 — tool chips + approval cards) ────
//
// Every test below is scoped to prove ONE thing: `pending` and `blocks` are
// purely additive. `ChatMessage`/`ChatWindowAdapter` gain optional fields;
// omitting them must render exactly what shipped before this slice.
describe("ChatWindow — no-blocks rendering is byte-identical to pre-seam (contract §E.7)", () => {
  it("adds zero seam markup and keeps the pre-seam 2-child bubble shape when blocks/pending are absent", () => {
    const { container } = render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Bom dia!")],
            isLoading: false,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));

    // The two new testids introduced by this slice must never appear on a
    // message that carries neither field — the additive-only guarantee.
    expect(screen.queryByTestId("chat-message-pending")).toBeNull();
    expect(screen.queryByTestId("chat-message-blocks")).toBeNull();

    // Structural pin: the bubble's content div has exactly the two <p>
    // children it had before this slice (body, timestamp). A regression
    // that always renders a blocks/pending wrapper would add a 3rd child.
    const messagesRoot = container.querySelector('[data-testid="chat-messages"]');
    const bubbleOuter = messagesRoot?.querySelector<HTMLElement>(":scope > div");
    const bubbleContent = bubbleOuter?.firstElementChild as HTMLElement | undefined;
    expect(bubbleContent).toBeTruthy();
    expect(bubbleContent!.children.length).toBe(2);
    expect(bubbleContent!.children[0].tagName).toBe("P");
    expect(bubbleContent!.children[0].textContent).toBe("Bom dia!");
    expect(bubbleContent!.children[1].tagName).toBe("P");
  });

  it("shows a pending indicator only on messages with pending=true", () => {
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [
              makeMessage("m1", "outbound", "Escrevendo", { pending: true }),
              makeMessage("m2", "inbound", "Mensagem normal"),
            ],
            isLoading: false,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));

    expect(screen.getByTestId("chat-message-pending")).toBeTruthy();
    expect(screen.getAllByTestId("chat-message-pending")).toHaveLength(1);
  });
});

describe("ChatWindow — tool block chips (contract §E.7)", () => {
  it("renders a tool block as a compact chip: name + status + resumo", () => {
    const toolBlock: ChatBlock = {
      kind: "tool",
      toolUseId: "tu1",
      name: "mcp__academia__kb_buscar",
      status: "ok",
      resumo: "3 resultados encontrados",
    };
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Buscando na KB...", { blocks: [toolBlock] })],
            isLoading: false,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));

    expect(screen.getByTestId("chat-tool-tu1")).toBeTruthy();
    expect(screen.getByText("mcp__academia__kb_buscar")).toBeTruthy();
    expect(screen.getByText("Concluído")).toBeTruthy();
    expect(screen.getByText("— 3 resultados encontrados")).toBeTruthy();
  });

  it("renders a running tool with no resumo (optional field omitted)", () => {
    const toolBlock: ChatBlock = {
      kind: "tool",
      toolUseId: "tu2",
      name: "kb_ler",
      status: "running",
    };
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Lendo...", { blocks: [toolBlock] })],
            isLoading: false,
            isError: false,
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));

    expect(screen.getByTestId("chat-tool-tu2")).toBeTruthy();
    expect(screen.getByText("Executando")).toBeTruthy();
  });
});

const APPROVAL_LABELS: Record<"pendente" | "aprovada" | "negada" | "expirada", string> = {
  pendente: "Pendente",
  aprovada: "Aprovada",
  negada: "Negada",
  expirada: "Expirada",
};

describe("ChatWindow — approval block cards (contract §E.7 / §E.2)", () => {
  function renderWithApproval(
    decision: "pendente" | "aprovada" | "negada" | "expirada",
    opts: { withApprovalAction?: boolean; isPending?: boolean; diff?: { antes: string | null; depois: string } } = {},
  ) {
    const decide = vi.fn().mockResolvedValue(undefined);
    const approvalBlock: ChatBlock = {
      kind: "approval",
      approvalId: "ap1",
      resumo: "Escrever decisão de arquitetura",
      decision,
      ...(opts.diff ? { diff: opts.diff } : {}),
    };
    render(
      <ChatWindow
        scopeId="scope-1"
        adapter={makeAdapter({
          useMessages: () => ({
            data: [makeMessage("m1", "inbound", "Posso escrever isso?", { blocks: [approvalBlock] })],
            isLoading: false,
            isError: false,
          }),
          ...(opts.withApprovalAction === false
            ? {}
            : { useApprovalAction: () => ({ decide, isPending: opts.isPending ?? false }) }),
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-thread-t1"));
    return { decide };
  }

  it("shows resumo + decision badge, and Aprovar/Negar when pendente AND the adapter provides useApprovalAction", () => {
    renderWithApproval("pendente");

    expect(screen.getByTestId("chat-approval-ap1")).toBeTruthy();
    expect(screen.getByText("Escrever decisão de arquitetura")).toBeTruthy();
    expect(screen.getByText("Pendente")).toBeTruthy();
    expect(screen.getByTestId("chat-approval-aprovar-ap1")).toBeTruthy();
    expect(screen.getByTestId("chat-approval-negar-ap1")).toBeTruthy();
  });

  it("clicking Aprovar calls decide(approvalId, true)", async () => {
    const { decide } = renderWithApproval("pendente");
    fireEvent.click(screen.getByTestId("chat-approval-aprovar-ap1"));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("ap1", true));
  });

  it("clicking Negar calls decide(approvalId, false)", async () => {
    const { decide } = renderWithApproval("pendente");
    fireEvent.click(screen.getByTestId("chat-approval-negar-ap1"));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("ap1", false));
  });

  it("disables both buttons while the adapter reports isPending (shared across the thread's approvals)", () => {
    renderWithApproval("pendente", { isPending: true });
    expect((screen.getByTestId("chat-approval-aprovar-ap1") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("chat-approval-negar-ap1") as HTMLButtonElement).disabled).toBe(true);
  });

  it.each(["aprovada", "negada", "expirada"] as const)(
    "hides Aprovar/Negar once decision is %s, even with useApprovalAction present",
    (decision) => {
      renderWithApproval(decision);
      expect(screen.getByTestId("chat-approval-ap1")).toBeTruthy();
      expect(screen.getByText(APPROVAL_LABELS[decision])).toBeTruthy();
      expect(screen.queryByTestId("chat-approval-aprovar-ap1")).toBeNull();
      expect(screen.queryByTestId("chat-approval-negar-ap1")).toBeNull();
    },
  );

  it("hides Aprovar/Negar when pendente but the adapter omits useApprovalAction (read-only card)", () => {
    renderWithApproval("pendente", { withApprovalAction: false });
    expect(screen.getByTestId("chat-approval-ap1")).toBeTruthy();
    expect(screen.queryByTestId("chat-approval-aprovar-ap1")).toBeNull();
    expect(screen.queryByTestId("chat-approval-negar-ap1")).toBeNull();
  });

  it("diff is collapsed by default and toggles open/closed on click", () => {
    renderWithApproval("pendente", { diff: { antes: "texto antigo", depois: "texto novo" } });

    expect(screen.queryByTestId("chat-approval-diff-ap1")).toBeNull();

    fireEvent.click(screen.getByTestId("chat-approval-diff-toggle-ap1"));
    const diffEl = screen.getByTestId("chat-approval-diff-ap1");
    expect(diffEl.textContent).toContain("texto antigo");
    expect(diffEl.textContent).toContain("texto novo");

    fireEvent.click(screen.getByTestId("chat-approval-diff-toggle-ap1"));
    expect(screen.queryByTestId("chat-approval-diff-ap1")).toBeNull();
  });

  it("renders '(vazio)' when diff.antes is null (a new KB entry, contract §D.1)", () => {
    renderWithApproval("pendente", { diff: { antes: null, depois: "conteúdo novo" } });
    fireEvent.click(screen.getByTestId("chat-approval-diff-toggle-ap1"));
    expect(screen.getByTestId("chat-approval-diff-ap1").textContent).toContain("(vazio)");
  });

  it("omits the diff toggle entirely when the block carries no diff", () => {
    renderWithApproval("pendente");
    expect(screen.queryByTestId("chat-approval-diff-toggle-ap1")).toBeNull();
  });
});

// ─── Link block (contract §G "Conversar", 2026-09-21) ──────────────────────

describe("ChatWindow — link block (in-app navigation row)", () => {
  it("renders a link block's label as an anchor pointing at href", () => {
    const linkBlock: ChatBlock = { kind: "link", label: "versão 3 · prompt sha256:abcd1234", href: "/studio/prompts/sha256:abcd1234" };
    const adapter = makeAdapter({
      useMessages: () => ({
        data: [makeMessage("m1", "inbound", "Aqui está o roteiro.", { blocks: [linkBlock] })],
        isLoading: false,
        isError: false,
      }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const link = screen.getByTestId("chat-link-block");
    expect(link.textContent).toBe("versão 3 · prompt sha256:abcd1234");
    expect(link.getAttribute("href")).toBe("/studio/prompts/sha256:abcd1234");
  });

  it("a tool block and a link block coexist on the same message", () => {
    const toolBlock: ChatBlock = { kind: "tool", toolUseId: "tu1", name: "kb_buscar", status: "ok" };
    const linkBlock: ChatBlock = { kind: "link", label: "versão 1 · prompt sha256:aaaa", href: "/studio/prompts/sha256:aaaa" };
    const adapter = makeAdapter({
      useMessages: () => ({
        data: [makeMessage("m1", "inbound", "Resposta.", { blocks: [toolBlock, linkBlock] })],
        isLoading: false,
        isError: false,
      }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    expect(screen.getByTestId("chat-tool-tu1")).toBeTruthy();
    expect(screen.getByTestId("chat-link-block")).toBeTruthy();
  });

  it("an https:// href renders as an anchor with rel=noopener noreferrer + target=_blank", () => {
    const linkBlock: ChatBlock = { kind: "link", label: "ver documentação", href: "https://example.com/docs" };
    const adapter = makeAdapter({
      useMessages: () => ({
        data: [makeMessage("m1", "inbound", "Veja.", { blocks: [linkBlock] })],
        isLoading: false,
        isError: false,
      }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const link = screen.getByTestId("chat-link-block");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe("https://example.com/docs");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("a same-origin relative path renders as an anchor with no target/rel", () => {
    const linkBlock: ChatBlock = { kind: "link", label: "ver versão", href: "/studio/prompts/sha256:aaaa" };
    const adapter = makeAdapter({
      useMessages: () => ({
        data: [makeMessage("m1", "inbound", "Veja.", { blocks: [linkBlock] })],
        isLoading: false,
        isError: false,
      }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const link = screen.getByTestId("chat-link-block");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("target")).toBeNull();
    expect(link.getAttribute("rel")).toBeNull();
  });

  it.each([
    ["javascript: URI", "javascript:alert(1)"],
    ["protocol-relative (off-origin) URL", "//evil.example.com/phish"],
    ["data: URI", "data:text/html,<script>alert(1)</script>"],
  ])("renders %s as inert plain text, never an anchor", (_label, href) => {
    const linkBlock: ChatBlock = { kind: "link", label: "clique aqui", href };
    const adapter = makeAdapter({
      useMessages: () => ({
        data: [makeMessage("m1", "inbound", "Cuidado.", { blocks: [linkBlock] })],
        isLoading: false,
        isError: false,
      }),
    });

    render(<ChatWindow scopeId="s1" adapter={adapter} />);
    fireEvent.click(screen.getByText("João Raphael"));

    const block = screen.getByTestId("chat-link-block");
    expect(block.tagName).not.toBe("A");
    expect(block.textContent).toBe("clique aqui");
  });
});
