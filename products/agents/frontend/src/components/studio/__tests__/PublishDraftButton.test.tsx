import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refs = vi.fn();
const isAdmin = vi.fn();
const compiled = vi.fn();
vi.mock("@/hooks/studio/useProntidao", () => ({
  useProntidao: () => ({ data: { pronto_para_publicar: true, itens: [] }, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: () => {} }),
}));
vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => refs(),
  useCreateDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePublishDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => isAdmin() }));
vi.mock("@/hooks/studio/useCompiled", () => ({ useCompiled: () => compiled() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { VersionBar } from "../ConteudoChrome";

const draft = { id: "d1", versao: 3, status: "rascunho", notas: null, eval_score: 0.9, compiled_hash: "abc" };
const ativa = { id: "a1", versao: 2, status: "ativa", notas: null, eval_score: 0.9, compiled_hash: "abc" };

beforeEach(() => {
  isAdmin.mockReturnValue(true);
  compiled.mockReturnValue({
    data: { hash: "abc", avisos: [{ codigo: "x", mensagem: "Seção vazia", bloqueante: true }] },
    showSkeleton: false,
    isError: false,
    refetch: vi.fn(),
  });
  refs.mockReturnValue({ data: { publicacao_limiar: 0.8, versoes: [draft, ativa] }, draft, ativa });
});
afterEach(cleanup);

describe("VersionBar publish", () => {
  it("shows the button on a draft and opens the dialog with blocking warnings", () => {
    render(<VersionBar agentKey="julia" rotulo="Decisões" />);
    fireEvent.click(screen.getByTestId("conteudo-publicar"));
    expect(screen.getByTestId("publish-bloqueantes").textContent).toContain("Seção vazia");
  });

  it("is disabled with a reason when the tab is dirty", () => {
    render(<VersionBar agentKey="julia" dirty />);
    expect((screen.getByTestId("conteudo-publicar") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("conteudo-publicar-dirty").textContent).toContain("Salve as alterações");
  });

  it("is hidden on a published (read-only) version and for non-admins", () => {
    refs.mockReturnValue({ data: { publicacao_limiar: 0.8, versoes: [ativa] }, draft: null, ativa });
    render(<VersionBar agentKey="julia" />);
    expect(screen.queryByTestId("conteudo-publicar")).toBeNull();
    cleanup();
    refs.mockReturnValue({ data: { publicacao_limiar: 0.8, versoes: [draft, ativa] }, draft, ativa });
    isAdmin.mockReturnValue(false);
    render(<VersionBar agentKey="julia" />);
    expect(screen.queryByTestId("conteudo-publicar")).toBeNull();
  });
});
