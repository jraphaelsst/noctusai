/**
 * Julia.tsx page tests — the controlled-selection wiring only (contract-free
 * UX seam, 2026-09-22). Stubs `@/hooks/useJuliaChat`'s `useCreateConversation`
 * and `@/components/JuliaChatWindow` so this asserts ONLY the page's own
 * logic: "Nova conversa" selects the conversation it just created. The
 * organ-level selection/rename mechanics live in the seed's own
 * `ChatWindow.test.tsx`; the adapter's optimistic rename lives in
 * `useJuliaChat.test.ts`.
 */
import React from "react";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockMutateAsync = vi.fn();

vi.mock("@/hooks/useJuliaChat", () => ({
  useCreateConversation: () => ({ mutateAsync: mockMutateAsync }),
}));

vi.mock("@/components/JuliaChatWindow", () => ({
  JuliaChatWindow: (props: { selectedThreadId?: string | null; onSelectThread?: (id: string | null) => void }) => (
    <div
      data-testid="julia-chat-window"
      data-selected-thread-id={props.selectedThreadId ?? ""}
      onClick={() => props.onSelectThread?.("clicked-from-organ")}
    />
  ),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => cleanup());

async function renderPage() {
  const Julia = (await import("@/pages/Julia")).default;
  render(React.createElement(Julia));
}

describe("Julia — auto-open the conversation 'Nova conversa' just created", () => {
  it("starts with no conversation selected", async () => {
    await renderPage();
    expect(screen.getByTestId("julia-chat-window").dataset.selectedThreadId).toBe("");
  });

  it("selects the new conversation's id the moment create resolves", async () => {
    mockMutateAsync.mockResolvedValue({ id: "conv-123", titulo: null });
    await renderPage();

    fireEvent.click(screen.getByTestId("julia-new-conversation"));

    await waitFor(() =>
      expect(screen.getByTestId("julia-chat-window").dataset.selectedThreadId).toBe("conv-123"),
    );
  });

  it("a click reported back from the organ (in-list navigation) updates the page's own selection", async () => {
    await renderPage();

    fireEvent.click(screen.getByTestId("julia-chat-window"));

    expect(screen.getByTestId("julia-chat-window").dataset.selectedThreadId).toBe("clicked-from-organ");
  });

  it("a failed create leaves the selection untouched — never fakes success", async () => {
    mockMutateAsync.mockRejectedValue(new Error("Falha ao criar conversa."));
    await renderPage();

    fireEvent.click(screen.getByTestId("julia-new-conversation"));

    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("julia-chat-window").dataset.selectedThreadId).toBe("");
  });
});
