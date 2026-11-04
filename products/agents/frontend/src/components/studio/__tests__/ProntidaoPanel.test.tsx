import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockUse = vi.fn();
vi.mock("@/hooks/studio/useProntidao", () => ({ useProntidao: () => mockUse() }));

import { ProntidaoPanel } from "@/components/studio/ProntidaoPanel";

afterEach(cleanup);
const view = (over: object) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over });

describe("ProntidaoPanel", () => {
  it("lists blocking items with the suggested action", () => {
    mockUse.mockReturnValue(
      view({
        data: {
          pronto_para_publicar: false,
          itens: [
            { codigo: "sem_avaliacao", grupo: "avaliacoes", severidade: "bloqueante", mensagem: "Sem avaliação", acao_sugerida: "Rode uma avaliação" },
            { codigo: "ok1", grupo: "conteudo", severidade: "ok", mensagem: "Textos completos", acao_sugerida: null },
          ],
        },
      }),
    );
    render(<ProntidaoPanel agentKey="a" />);
    expect(screen.getByTestId("prontidao-titulo").textContent).toContain("Faltam 1 item bloqueante");
    expect(screen.getByTestId("prontidao-acao-sem_avaliacao").textContent).toBe("Rode uma avaliação");
  });

  it("shows ready header", () => {
    mockUse.mockReturnValue(view({ data: { pronto_para_publicar: true, itens: [] } }));
    render(<ProntidaoPanel agentKey="a" />);
    expect(screen.getByTestId("prontidao-titulo").textContent).toContain("Pronto para publicar");
  });

  it("renders the server 409 prontidao over the query", () => {
    mockUse.mockReturnValue(view({ data: { pronto_para_publicar: true, itens: [] } }));
    render(
      <ProntidaoPanel
        agentKey="a"
        override={{ pronto_para_publicar: false, itens: [{ codigo: "x", grupo: "skills", severidade: "bloqueante", mensagem: "Skill velha", acao_sugerida: null }] }}
      />,
    );
    expect(screen.getByText("Skill velha")).toBeTruthy();
  });

  it("shows an error, never a silent ready", () => {
    mockUse.mockReturnValue(view({ isError: true, error: new Error("falhou") }));
    render(<ProntidaoPanel agentKey="a" />);
    expect(screen.queryByTestId("prontidao-titulo")).toBeNull();
  });
});
