/** QualificacaoTab — the platform standard: grouping, per-criterion save, publish 422 rule errors, restricted state. */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { PADRAO_VERSAO } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});

import QualificacaoTab from "../QualificacaoTab";

const V = PADRAO_VERSAO.id;
const base = [
  { method: "GET" as const, path: "/api/qualificacao/padroes", body: { items: [{ id: "p1", chave: "padrao-x", nome: "Padrão X", descricao: null }] } },
  {
    method: "GET" as const,
    path: "/api/qualificacao/padroes/padrao-x/versoes",
    body: { items: [{ id: V, versao: 3, status: "rascunho", notas: null, publicada_em: null }, { id: "pub", versao: 2, status: "publicada", notas: null, publicada_em: "2026-10-01T00:00:00Z" }] },
  },
  { method: "GET" as const, path: `/api/qualificacao/versoes/${V}`, body: PADRAO_VERSAO },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("QualificacaoTab", () => {
  it("groups criteria by escopo and eixo and shows stages and parameters", async () => {
    installFetch(base);
    renderWith(<QualificacaoTab agentKey="x" />);
    const sdr = await screen.findByTestId("qual-escopo-sdr");
    expect(within(sdr).getByTestId("criterio-crit_a")).toBeTruthy();
    expect(within(sdr).getByText("Eixo: eixo_1")).toBeTruthy();
    expect(screen.getByTestId("qual-escopo-financeiro")).toBeTruthy();
    expect(screen.getByTestId("estagio-est_a")).toBeTruthy();
    expect(screen.getByTestId("qual-parametros")).toBeTruthy();
    expect(screen.getByTestId("qual-estado").textContent).toContain("Rascunho v3");
  });

  it("saves one criterion with a PUT of its fields (no chave in the body)", async () => {
    const net = installFetch([
      ...base,
      { method: "PUT", path: `/api/qualificacao/versoes/${V}/criterios/crit_a`, body: PADRAO_VERSAO },
    ]);
    renderWith(<QualificacaoTab agentKey="x" />);
    const det = await screen.findByTestId("criterio-crit_a");
    fireEvent.change(within(det).getByLabelText("Rótulo"), { target: { value: "Critério A2" } });
    fireEvent.click(within(det).getByTestId("criterio-salvar-crit_a"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    const body = net.calls.find((c) => c.method === "PUT")!.body as Record<string, unknown>;
    expect(body.rotulo).toBe("Critério A2");
    expect(body.pontuacao).toEqual({ op1: 10 });
    expect("chave" in body).toBe(false);
  });

  it("blocks saving a criterion whose rule JSON is invalid", async () => {
    installFetch(base);
    renderWith(<QualificacaoTab agentKey="x" />);
    const det = await screen.findByTestId("criterio-crit_a");
    fireEvent.change(within(det).getByLabelText("Pontuação (pontos por opção ou faixas)"), { target: { value: "{ quebrado" } });
    expect(within(det).getByText("JSON inválido")).toBeTruthy();
    expect((within(det).getByTestId("criterio-salvar-crit_a") as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders every rule error of a refused publish (422 regras_invalidas)", async () => {
    installFetch([
      ...base,
      {
        method: "POST",
        path: `/api/qualificacao/versoes/${V}/publicar`,
        status: 422,
        body: {
          detail: "A versao nao pode ser publicada.",
          code: "regras_invalidas",
          erros: [
            { code: "criterio_desconhecido", path: "estagios.est_a.regra", detail: "referência a critério inexistente" },
            { code: "parametros_ausentes", path: "parametros", detail: "defina os parametros" },
          ],
        },
      },
    ]);
    renderWith(<QualificacaoTab agentKey="x" />);
    fireEvent.click(await screen.findByTestId("qual-publicar"));
    const botoes = await screen.findAllByRole("button", { name: /Publicar/ });
    fireEvent.click(botoes[botoes.length - 1]); // the confirmation dialog's button
    const box = await screen.findByTestId("qual-regra-erros");
    expect(box.textContent).toContain("estagios.est_a.regra");
    expect(box.textContent).toContain("defina os parametros");
  });

  it("shows the restricted state for a non platform admin (403)", async () => {
    installFetch([{ method: "GET", path: "/api/qualificacao/padroes", status: 403, body: { detail: "x", code: "platform_admin_required" } }]);
    renderWith(<QualificacaoTab agentKey="x" />);
    expect((await screen.findByTestId("studio-restrito")).textContent).toContain("administradores da plataforma");
  });
});
