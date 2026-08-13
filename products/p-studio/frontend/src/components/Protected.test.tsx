/**
 * Guarda de rota.
 *
 * O protótipo não tinha nenhuma: visitante anônimo chegava em `/financeiro`.
 * Esta é a regressão que mais importa travar — daí os testes cobrirem os
 * quatro estados (carregando / sem sessão / perfil quebrado / autenticado) e,
 * em particular, que *nenhum* deles vaza o conteúdo protegido.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const estadoAuth = {
  session: null as unknown,
  me: null as unknown,
  loading: false,
  error: null as string | null,
  signOut: vi.fn(),
};

vi.mock("@/stores/auth", () => ({
  useAuth: () => estadoAuth,
}));

vi.mock("@/components/AppLayout", () => ({
  default: () => <div data-testid="app-layout">conteúdo protegido</div>,
}));

const { Protected } = await import("@/components/Protected");

function montar() {
  return render(
    <MemoryRouter initialEntries={["/financeiro"]}>
      <Routes>
        <Route path="/financeiro" element={<Protected />} />
        <Route path="/login" element={<div data-testid="login">tela de login</div>} />
      </Routes>
    </MemoryRouter>
  );
}

const SESSAO = { user: { id: "u1" } };
const PERFIL = { id: "u1", email: "equipe@pstudio.app", nome: "Equipe", org_id: "o1" };

beforeEach(() => {
  estadoAuth.session = null;
  estadoAuth.me = null;
  estadoAuth.loading = false;
  estadoAuth.error = null;
  estadoAuth.signOut = vi.fn();
});

describe("Protected", () => {
  it("enquanto carrega não decide nada — nem conteúdo nem redirect", () => {
    estadoAuth.loading = true;
    montar();

    expect(screen.queryByTestId("app-layout")).not.toBeInTheDocument();
    expect(screen.queryByTestId("login")).not.toBeInTheDocument();
  });

  it("sem sessão redireciona para /login", () => {
    montar();

    expect(screen.getByTestId("login")).toBeInTheDocument();
    expect(screen.queryByTestId("app-layout")).not.toBeInTheDocument();
  });

  it("com sessão e perfil renderiza o app", () => {
    estadoAuth.session = SESSAO;
    estadoAuth.me = PERFIL;
    montar();

    expect(screen.getByTestId("app-layout")).toBeInTheDocument();
  });

  it("sessão válida mas backend fora mostra o erro em vez do app", () => {
    estadoAuth.session = SESSAO;
    estadoAuth.error = "Failed to fetch";
    montar();

    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
    expect(screen.queryByTestId("app-layout")).not.toBeInTheDocument();
  });

  it("erro orienta a checar o backend na porta certa", () => {
    estadoAuth.session = SESSAO;
    estadoAuth.error = "Failed to fetch";
    montar();

    expect(screen.getByText(/porta 8020/)).toBeInTheDocument();
  });

  it("sessão sem perfil e sem erro também não libera o app", () => {
    estadoAuth.session = SESSAO;
    estadoAuth.me = null;
    montar();

    expect(screen.queryByTestId("app-layout")).not.toBeInTheDocument();
    expect(screen.getByText(/não foi possível carregar seu perfil/i)).toBeInTheDocument();
  });

  it("o botão de sair no estado de erro chama signOut", async () => {
    estadoAuth.session = SESSAO;
    estadoAuth.error = "Failed to fetch";
    montar();

    await userEvent.click(screen.getByRole("button", { name: /sair/i }));
    expect(estadoAuth.signOut).toHaveBeenCalledTimes(1);
  });

  it("nenhum estado não-autenticado vaza o conteúdo protegido", () => {
    const cenarios = [
      { loading: true },
      { session: null },
      { session: SESSAO, error: "boom" },
      { session: SESSAO, me: null },
    ];

    for (const cenario of cenarios) {
      estadoAuth.session = null;
      estadoAuth.me = null;
      estadoAuth.loading = false;
      estadoAuth.error = null;
      Object.assign(estadoAuth, cenario);

      const { unmount } = montar();
      expect(screen.queryByTestId("app-layout")).not.toBeInTheDocument();
      unmount();
    }
  });
});
