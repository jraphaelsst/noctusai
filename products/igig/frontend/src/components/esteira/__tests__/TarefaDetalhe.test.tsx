/**
 * TarefaDetalhe — delete flow (tech-lead addendum, 2026-09).
 *
 * Before this fix, `confirmarExclusao` sent `confirmarPerdaHoras:
 * minutosTotais > 0` — a client-side guess that reads 0 (and so never asks)
 * for a sub-minute or still-RUNNING apontamento, while the backend 409s
 * `horas_serao_perdidas` on ANY apontamento regardless of its minutes. That
 * made deleting such a tarefa impossible: every click sent `false`, every
 * click 409'd, no button ever flipped the flag.
 *
 * These tests pin the fix: the first attempt never forces it; a 409 shows
 * the SERVER's own message and flips the button to "Excluir mesmo assim",
 * which retries with `confirmarPerdaHoras: true`; a running timer is
 * encerrado BEFORE the delete attempt.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";

const mockUseApontamentos = vi.fn();
const mockIniciar = { mutate: vi.fn(), isPending: false };
const mockEncerrar = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
const mockEmitirLink = { mutate: vi.fn(), isPending: false };
const mockAtualizar = { mutate: vi.fn(), isPending: false };
const mockExcluir = { mutate: vi.fn(), isPending: false };

vi.mock("@/hooks/useEsteira", () => ({
  urlAprovacao: (token: string) => `https://example.test/aprovar/${token}`,
  useApontamentos: () => mockUseApontamentos(),
  useIniciarTimer: () => mockIniciar,
  useEncerrarTimer: () => mockEncerrar,
  useEmitirLinkAprovacao: () => mockEmitirLink,
  useAtualizarTarefa: () => mockAtualizar,
  useExcluirTarefa: () => mockExcluir,
}));

vi.mock("@/hooks/useCustos", () => ({ useProfissionais: () => ({ profissionais: [] }) }));
vi.mock("@/hooks/usePautas", () => ({ usePautas: () => ({ pautas: [] }) }));
vi.mock("@/hooks/useClientes", () => ({ useClientes: () => ({ clientes: [] }) }));
vi.mock("@/components/RepertorioSidebar", () => ({ RepertorioSidebar: () => null }));

import { TarefaDetalhe } from "../TarefaDetalhe";
import type { TarefaCard } from "@/hooks/useEsteira";

const TAREFA: TarefaCard = {
  id: "t1", org_id: "org1", pauta_id: "p1", cliente_id: "c1", titulo: "Arte do post",
  etapa_id: "e1", responsavel_id: null, prazo: null, refacoes: 0, observacao_cliente: null,
  created_at: null, updated_at: null,
  pauta: { id: "p1", titulo: "Post", formato: null, data_publicacao: null, marca_id: null },
  cliente: { id: "c1", nome: "Padaria Sol" }, responsavel: null,
};

function renderDetalhe() {
  return render(
    <TarefaDetalhe tarefa={TAREFA} etapaLabel="Em produção" usuarioId="u1" onClose={vi.fn()} />,
  );
}

function abrirModoExcluir() {
  fireEvent.click(screen.getByTestId("tarefa-excluir"));
}

beforeEach(() => {
  vi.clearAllMocks();
  mockExcluir.isPending = false;
  mockEncerrar.isPending = false;
  mockUseApontamentos.mockReturnValue({
    apontamentos: [], emAndamento: null, minutosTotais: 0, loading: false, error: null,
  });
});

describe("TarefaDetalhe — deleting with sub-minute or running apontamentos", () => {
  it("the first delete attempt never forces confirmarPerdaHoras", () => {
    mockUseApontamentos.mockReturnValue({
      apontamentos: [{ id: "a1", minutos: 0 }], emAndamento: null, minutosTotais: 0,
      loading: false, error: null,
    });
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));
    expect(mockExcluir.mutate).toHaveBeenCalledWith(
      { id: "t1", confirmarPerdaHoras: false },
      expect.anything(),
    );
  });

  it("shows the SERVER's own message on a 409 and offers 'Excluir mesmo assim'", () => {
    mockUseApontamentos.mockReturnValue({
      apontamentos: [{ id: "a1", minutos: 0 }], emAndamento: null, minutosTotais: 0,
      loading: false, error: null,
    });
    mockExcluir.mutate.mockImplementation((_vars, { onError }) => {
      onError(new ApiError(409, "Isto tem 0 min de horas apontadas em 1 apontamento.", {
        detail: "Isto tem 0 min de horas apontadas em 1 apontamento.",
        code: "horas_serao_perdidas",
      }));
    });
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));

    expect(screen.getByText("Isto tem 0 min de horas apontadas em 1 apontamento.")).toBeInTheDocument();
    expect(screen.getByTestId("tarefa-confirmar-exclusao")).toHaveTextContent("Excluir mesmo assim");
  });

  it("the SECOND click (after the 409) retries with confirmarPerdaHoras: true", () => {
    mockUseApontamentos.mockReturnValue({
      apontamentos: [{ id: "a1", minutos: 0 }], emAndamento: null, minutosTotais: 0,
      loading: false, error: null,
    });
    let chamadas = 0;
    mockExcluir.mutate.mockImplementation((vars, { onError, onSuccess }) => {
      chamadas += 1;
      if (chamadas === 1) {
        onError(new ApiError(409, "perda", { code: "horas_serao_perdidas" }));
      } else {
        onSuccess(null);
      }
    });
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao")); // 1st: 409
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao")); // 2nd: forces it
    expect(mockExcluir.mutate).toHaveBeenLastCalledWith(
      { id: "t1", confirmarPerdaHoras: true },
      expect.anything(),
    );
  });

  it("an unrelated delete error is toasted, not treated as the hours warning", () => {
    mockExcluir.mutate.mockImplementation((_vars, { onError }) => {
      onError(new ApiError(500, "boom", {}));
    });
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));
    expect(screen.queryByTestId("tarefa-detalhe-note")).not.toBeInTheDocument();
  });
});

describe("TarefaDetalhe — a running timer is stopped before deleting", () => {
  it("encerra the timer BEFORE attempting the delete when one is running", async () => {
    mockUseApontamentos.mockReturnValue({
      apontamentos: [{ id: "a1", minutos: 0, encerrado_em: null }],
      emAndamento: { id: "a1", minutos: 0, encerrado_em: null }, minutosTotais: 0,
      loading: false, error: null,
    });
    mockEncerrar.mutateAsync.mockResolvedValue({ id: "a1" });
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));

    await waitFor(() => expect(mockEncerrar.mutateAsync).toHaveBeenCalledWith("t1"));
    expect(mockExcluir.mutate).toHaveBeenCalled();
  });

  it("does not attempt the delete when stopping the timer fails", async () => {
    mockUseApontamentos.mockReturnValue({
      apontamentos: [{ id: "a1", minutos: 0, encerrado_em: null }],
      emAndamento: { id: "a1", minutos: 0, encerrado_em: null }, minutosTotais: 0,
      loading: false, error: null,
    });
    mockEncerrar.mutateAsync.mockRejectedValue(new ApiError(500, "boom", {}));
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));

    await waitFor(() => expect(mockEncerrar.mutateAsync).toHaveBeenCalled());
    expect(mockExcluir.mutate).not.toHaveBeenCalled();
  });

  it("does not try to stop a timer that is not running", () => {
    renderDetalhe();
    abrirModoExcluir();
    fireEvent.click(screen.getByTestId("tarefa-confirmar-exclusao"));
    expect(mockEncerrar.mutateAsync).not.toHaveBeenCalled();
    expect(mockExcluir.mutate).toHaveBeenCalled();
  });
});
