import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockUse = vi.fn();
vi.mock("@/hooks/studio/useProntidao", () => ({ useProntidao: () => mockUse() }));

vi.mock("@/components/studio/ProntidaoAcao", async (orig) => ({ ...(await orig<object>()), ProntidaoAcao: ({ codigo }: { codigo: string }) => <button type="button">acao-{codigo}</button> }));

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
            { codigo: "sem_avaliacao", grupo: "avaliacao", severidade: "bloqueante", mensagem: "Sem avaliação", acao_sugerida: "Rode uma avaliação" },
            { codigo: "ok1", grupo: "conteudo", severidade: "ok", mensagem: "Textos completos", acao_sugerida: null },
          ],
        },
      }),
    );
    render(<ProntidaoPanel agentKey="a" />);
    expect(screen.getByTestId("prontidao-titulo").textContent).toContain("Faltam 1 item bloqueante");
    expect(screen.getByTestId("prontidao-acao-sem_avaliacao").textContent).toBe("Rode uma avaliação");
  });

  it("shows each base of the chain gate with its verdict", () => {
    const camada = (over: object) => ({ agent_key: "agente-base", versao: 3, validada: true, motivo: "validada", criticos_total: 4, criticos_consolidados: 4, criticos_pendentes: [], ...over });
    mockUse.mockReturnValue(
      view({
        data: {
          pronto_para_publicar: false,
          itens: [
            {
              codigo: "base_nao_validada", grupo: "avaliacao", severidade: "bloqueante", mensagem: "A base não está validada", acao_sugerida: null,
              detalhe: { camadas: [camada({}), camada({ agent_key: "sdr-base", versao: null, validada: false, motivo: "criticos_pendentes", criticos_pendentes: ["a", "b"] })] },
            },
          ],
        },
      }),
    );
    render(<ProntidaoPanel agentKey="julia" />);
    expect(screen.getByTestId("prontidao-base-agente-base").textContent).toBe("Base: agente-base ✓ validada (v3)");
    expect(screen.getByTestId("prontidao-base-sdr-base").textContent).toBe("Base: sdr-base ✗ não validada — 2 casos críticos pendentes");
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

  it("renders a button instead of the API-path text for fixable items", () => {
    mockUse.mockReturnValue(view({ data: { pronto_para_publicar: false, itens: [
      { codigo: "mecanismo_hash_diferente", grupo: "avaliacao", severidade: "bloqueante", mensagem: "Suíte velha", acao_sugerida: "Clique em Rodar suíte de mecanismo" },
    ] } }));
    render(<ProntidaoPanel agentKey="a" />);
    expect(screen.getByRole("button", { name: "acao-mecanismo_hash_diferente" })).toBeTruthy();
    expect(screen.queryByTestId("prontidao-acao-mecanismo_hash_diferente")).toBeNull();
  });
});
