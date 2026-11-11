/**
 * PromptTab.tsx — a section's declared RULES (Q2): shown as read-only chips, and sent back on save so the editor
 * never silently clears them (the PUT is a full replace).
 */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockRefs = vi.fn();
const mockVersion = vi.fn();
const mockSave = vi.fn();

vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => mockRefs(),
  useVersion: () => mockVersion(),
  useCreateDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSaveSections: () => mockSave(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));
vi.mock("@/hooks/studio/useGeracoes", () => ({ useItensGerados: () => ({ secoes: {} }) }));
vi.mock("@/components/studio/PublishDraftDialog", () => ({ PublishDraftButton: () => null }));

const DRAFT = { id: "v2", versao: 2, status: "rascunho" as const };
const DETAIL = {
  ...DRAFT,
  secoes: [
    { id: "s1", chave: "honestidade", titulo: "Honestidade", ordem: 10, conteudo: "Discorde com respeito.", ativo: true, regras: ["discordar-com-respeito"] },
    { id: "s2", chave: "persona", titulo: "Persona", ordem: 20, conteudo: "Você é a Julia.", ativo: true, regras: [] },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockRefs.mockReturnValue({ data: {}, draft: DRAFT, ativa: null, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), isPlaceholderData: false });
  mockVersion.mockReturnValue({ data: DETAIL, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), isPlaceholderData: false });
});
afterEach(() => cleanup());

describe("PromptTab — section rules", () => {
  it("shows the rule as a chip and sends it back unchanged on save", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(DETAIL);
    mockSave.mockReturnValue({ mutateAsync, isPending: false });
    const PromptTab = (await import("@/pages/studio/tabs/PromptTab")).default;
    render(React.createElement(MemoryRouter, null, React.createElement(PromptTab, { agentKey: "julia" })));

    expect(screen.getByText("Regra: discordar-com-respeito")).toBeTruthy();
    expect(screen.getAllByText(/^Regra:/)).toHaveLength(1);

    // Reorder so the form is dirty (Save is disabled otherwise); the rules must travel with their sections.
    fireEvent.click(screen.getAllByLabelText("Descer")[0]);
    fireEvent.click(screen.getByTestId("prompt-save"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const secoes = mutateAsync.mock.calls[0][0].secoes;
    expect(secoes.map((s: { regras: string[] }) => s.regras)).toEqual([[], ["discordar-com-respeito"]]);
  }, 90_000);
});
