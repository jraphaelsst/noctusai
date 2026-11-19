/** AprovacaoAcoes: approve, reject-with-required-reason, disabled reason as text, refusal never silent. */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ mutate: vi.fn(), toastErr: vi.fn(), toastOk: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: m.toastOk, error: m.toastErr } }));
vi.mock("@/hooks/geracao/useCriacao", () => ({
  useAprovarEtapa: () => ({ mutate: m.mutate, isPending: false }),
  mensagemAprovacao: (e: any) => e?.message ?? "falha",
}));

import { AprovacaoAcoes } from "./AprovacaoAcoes";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AprovacaoAcoes", () => {
  it("Aprovar envia alvo e decisão", () => {
    render(<AprovacaoAcoes postId="p1" alvo="roteiro" aprovado={false} disponivel />);
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    expect(m.mutate.mock.calls[0][0]).toEqual({ postId: "p1", alvo: "roteiro", decisao: "aprovar", motivo: undefined });
  });

  it("Reprovar exige motivo e o envia", async () => {
    render(<AprovacaoAcoes postId="p1" alvo="headline" aprovado={false} disponivel />);
    fireEvent.click(screen.getByRole("button", { name: /Reprovar/ }));
    expect(screen.getByRole("button", { name: "Devolver para refinar" })).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("O que precisa mudar?"), { target: { value: "muito genérica" } });
    fireEvent.click(screen.getByRole("button", { name: "Devolver para refinar" }));
    await waitFor(() => expect(m.mutate).toHaveBeenCalled());
    expect(m.mutate.mock.calls[0][0]).toMatchObject({ decisao: "reprovar", motivo: "muito genérica" });
  });

  it("indisponível: botões desabilitados e o motivo aparece como texto", () => {
    render(
      <AprovacaoAcoes postId="p1" alvo="roteiro" aprovado={false} disponivel={false} indisponivelMotivo="Disponível quando o roteiro estiver completo." />,
    );
    expect(screen.getByRole("button", { name: /Aprovar/ })).toBeDisabled();
    expect(screen.getByText("Disponível quando o roteiro estiver completo.")).toBeInTheDocument();
  });

  it("aprovado: mostra o estado e some o botão Aprovar", () => {
    render(<AprovacaoAcoes postId="p1" alvo="midia" aprovado disponivel />);
    expect(screen.getByText("Mídia aprovada")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Aprovar/ })).toBeNull();
  });

  it("recusa do servidor vira toast de erro", () => {
    m.mutate.mockImplementation((_v: any, o: any) => o.onError(new Error("O limite mensal foi atingido")));
    render(<AprovacaoAcoes postId="p1" alvo="roteiro" aprovado={false} disponivel />);
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    expect(m.toastErr).toHaveBeenCalledWith("O limite mensal foi atingido");
  });
});
