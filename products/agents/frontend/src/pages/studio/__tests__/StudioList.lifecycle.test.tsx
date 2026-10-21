import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const agents = vi.fn();
vi.mock("@/hooks/studio/useStudioAgents", () => ({
  useStudioAgents: () => agents(),
  useStudioAgent: () => ({ data: undefined }),
  useUpdateStudioAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateStudioAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));
vi.mock("@/hooks/useIsPlatformAdmin", () => ({ useIsPlatformAdmin: () => true }));
vi.mock("@/components/studio/ContentTokenCard", () => ({ ContentTokenCard: () => null }));
vi.mock("@/components/studio/CriarAgentePlataformaDialog", () => ({ CriarAgentePlataformaDialog: () => <div data-testid="dlg-criar" /> }));
vi.mock("@/components/studio/ExcluirAgenteDialog", () => ({
  ExcluirAgenteDialog: ({ agentKey }: { agentKey: string }) => <div data-testid={`dlg-excluir-${agentKey}`} />,
}));

import StudioList from "../StudioList";

const base = {
  id: "1", key: "julia", nome: "Julia", descricao: null, definition_mode: "studio", ativo: false,
  publicacao_limiar: 0.8, versao_ativa: null, tem_rascunho: false, kind: "runtime", definition_scope: "plataforma",
};
const view = (items: object[]) => ({ data: items, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn() });

afterEach(cleanup);

describe("StudioList lifecycle", () => {
  it("renders an empty shell cleanly with progress, opens create and delete", () => {
    agents.mockReturnValue(view([{ ...base, conteudo_status: { preenchidos: 0, exigidos: 12 } }]));
    render(<MemoryRouter><StudioList /></MemoryRouter>);
    expect(screen.getByTestId("studio-conteudo-julia").textContent).toBe("0 de 12 textos");
    expect(screen.queryByTestId("studio-list-skeleton")).toBeNull();
    fireEvent.click(screen.getByTestId("studio-criar-agente"));
    expect(screen.getByTestId("dlg-criar")).toBeTruthy();
    fireEvent.click(screen.getByTestId("studio-excluir-julia"));
    expect(screen.getByTestId("dlg-excluir-julia")).toBeTruthy();
  });

  it("shows no progress numbers when the server omits conteudo_status", () => {
    agents.mockReturnValue(view([base]));
    render(<MemoryRouter><StudioList /></MemoryRouter>);
    expect(screen.queryByTestId("studio-conteudo-julia")).toBeNull();
  });
});
