/** SwCanalCard — states (skeleton / error / ausente / provisionado / erro), the test button (success + failure) and: the card
 * never shows, asks for or accepts a credential value. Runs the real hooks over the network fake. */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { renderWith } from "@/pages/studio/tabs/__tests__/harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});

import { SwCanalCard } from "../SwCanalCard";

const URL = "/api/studio/plataforma/sw-canal";
const status = (over: object = {}) => ({
  estado: "provisionado", escopo: "social-wiring:onboarding-settings", emissor: "noctus-platform",
  expira_em: "2026-12-18T12:00:00Z", dias_restantes: 30, ultima_chamada_ok: null, ultimo_erro: null, codigo: null, motivo: null, ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SwCanalCard", () => {
  it("shows a skeleton while loading", () => {
    installFetch([{ method: "GET", path: URL, body: status() }]);
    renderWith(<SwCanalCard />);
    expect(screen.getByTestId("sw-canal-skeleton")).toBeTruthy();
  });

  it("shows a visible error with retry when the state cannot be read (never a blank card)", async () => {
    installFetch([{ method: "GET", path: URL, status: 502, body: { code: "status_indisponivel", detail: "x" } }]);
    renderWith(<SwCanalCard />);
    const err = await screen.findByTestId("studio-error");
    expect(err.textContent).toContain("Não foi possível ler o estado da conexão.");
    expect(screen.getByText("Tentar novamente")).toBeTruthy();
  });

  it("ausente: says it is created by itself, with no field to type or paste anything", async () => {
    installFetch([{ method: "GET", path: URL, body: status({ estado: "ausente", expira_em: null, dias_restantes: null }) }]);
    const { container } = renderWith(<SwCanalCard />);
    expect((await screen.findByTestId("sw-canal-estado")).textContent).toBe("Ausente");
    expect(screen.getByTestId("sw-canal-descricao").textContent).toContain("criada sozinha");
    expect(container.querySelectorAll("input, textarea").length).toBe(0);
    expect(screen.getByTestId("sw-canal-ultima-ok").textContent).toContain("Nenhum até agora");
  });

  it("provisionado: scope, expiry, last ok call and last error with the pt-BR reason", async () => {
    installFetch([{
      method: "GET", path: URL,
      body: status({
        ultima_chamada_ok: { em: "2026-11-18T10:00:00Z", evento: "sw_canal_chamada_concluida", codigo: null, motivo: null },
        ultimo_erro: { em: "2026-11-17T09:00:00Z", evento: "sw_canal_conexao_testada", codigo: "sw_unreachable", motivo: "Serviço de destino indisponível." },
      }),
    }]);
    renderWith(<SwCanalCard />);
    expect((await screen.findByTestId("sw-canal-estado")).textContent).toBe("Provisionado");
    expect(screen.getByTestId("sw-canal-escopo").textContent).toContain("social-wiring:onboarding-settings");
    expect(screen.getByTestId("sw-canal-expira").textContent).toContain("30 dia(s)");
    expect(screen.getByTestId("sw-canal-ultimo-erro").textContent).toContain("Serviço de destino indisponível.");
    expect(screen.getByTestId("sw-canal-ultima-ok").textContent).not.toContain("Nenhum");
  });

  it("erro: shows the named reason as an alert", async () => {
    installFetch([{ method: "GET", path: URL, body: status({ estado: "erro", codigo: "token_revogado", motivo: "O token foi revogado; será gerado outro no próximo uso." }) }]);
    renderWith(<SwCanalCard />);
    expect((await screen.findByTestId("sw-canal-motivo")).textContent).toContain("revogado");
  });

  it("Testar conexão: success provisions, updates the state in place and says it works", async () => {
    const provisionado = status({ ultima_chamada_ok: { em: "2026-11-18T10:00:00Z", evento: "sw_canal_conexao_testada", codigo: null, motivo: null } });
    const net = installFetch([
      { method: "GET", path: URL, bodies: [status({ estado: "ausente", expira_em: null, dias_restantes: null }), provisionado] },
      {
        method: "POST", path: `${URL}/testar`,
        body: { ok: true, codigo: null, motivo: "Conexão com o Social Wiring funcionando.", status: status({ ultima_chamada_ok: { em: "2026-11-18T10:00:00Z", evento: "sw_canal_conexao_testada", codigo: null, motivo: null } }) },
      },
    ]);
    renderWith(<SwCanalCard />);
    await screen.findByTestId("sw-canal-estado");
    fireEvent.click(screen.getByTestId("sw-canal-testar"));
    expect((await screen.findByTestId("sw-canal-resultado")).textContent).toContain("Conexão funcionando");
    await waitFor(() => expect(screen.getByTestId("sw-canal-estado").textContent).toBe("Provisionado"));
    expect(net.calls.filter((c) => c.method === "POST").length).toBe(1);
  });

  it("Testar conexão: a failure shows its reason and the last error, never swallowed", async () => {
    const motivo = "Credencial aceita mas sem permissão (403) — escopo ou emissor incorreto.";
    const comErro = status({ ultimo_erro: { em: "2026-11-18T10:05:00Z", evento: "sw_canal_conexao_testada", codigo: "sw_forbidden", motivo } });
    installFetch([
      { method: "GET", path: URL, bodies: [status(), comErro] },
      { method: "POST", path: `${URL}/testar`, body: { ok: false, codigo: "sw_forbidden", motivo, status: comErro } },
    ]);
    renderWith(<SwCanalCard />);
    await screen.findByTestId("sw-canal-estado");
    fireEvent.click(screen.getByTestId("sw-canal-testar"));
    const r = await screen.findByTestId("sw-canal-resultado");
    expect(r.textContent).toContain("Falhou:");
    expect(r.textContent).toContain("escopo ou emissor incorreto");
    await waitFor(() => expect(screen.getByTestId("sw-canal-ultimo-erro").textContent).toContain("403"));
  });

  it("Testar conexão: an HTTP failure of the test itself is shown as an alert", async () => {
    installFetch([
      { method: "GET", path: URL, body: status() },
      { method: "POST", path: `${URL}/testar`, status: 502, body: { code: "teste_indisponivel", detail: "Não foi possível testar a conexão." } },
    ]);
    renderWith(<SwCanalCard />);
    await screen.findByTestId("sw-canal-estado");
    fireEvent.click(screen.getByTestId("sw-canal-testar"));
    expect((await screen.findByTestId("sw-canal-teste-erro")).textContent).toContain("Não foi possível testar");
  });
});
