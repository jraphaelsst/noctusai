/** EspecificacoesOrgTab — the org admin's own values form and the inline refusals (CONTRACT §2.6). */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { KEY } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import EspecificacoesOrgTab from "../EspecificacoesOrgTab";

const P = `/api/studio/agents/${KEY}/specs`;
const SPECS = {
  agent_key: KEY,
  version_id: "v1",
  versao: 1,
  declaradas: [
    { id: "s1", chave: "nome_org", rotulo: "Nome da organização", descricao: "Como a empresa se apresenta.", tipo: "texto", obrigatoria: true, exemplo: "Empresa Exemplo" },
    { id: "s2", chave: "regioes", rotulo: "Regiões atendidas", descricao: "", tipo: "texto_longo", obrigatoria: false, exemplo: null },
  ],
  valores: [{ chave: "regioes", valor: "região sintética", updated_at: null }],
  faltando: ["nome_org"],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("EspecificacoesOrgTab", () => {
  it("renders the declared form with missing markers and the locked-block label", async () => {
    installFetch([{ method: "GET", path: P, body: SPECS }]);
    renderWith(<EspecificacoesOrgTab agentKey={KEY} />);
    expect(await screen.findByTestId("spec-org-nome_org")).toBeTruthy();
    expect(screen.getByTestId("specs-faltando").textContent).toContain("1 obrigatória");
    expect(screen.getByTestId("specs-bloco-travado")).toBeTruthy();
    expect((screen.getByLabelText(/Regiões atendidas/) as HTMLTextAreaElement).value).toBe("região sintética");
  });

  it("PUTs every declared key (blank clears) and refetches", async () => {
    const net = installFetch([
      { method: "GET", path: P, body: SPECS },
      { method: "PUT", path: P, body: { ...SPECS, faltando: [] } },
      { method: "GET", path: `/api/studio/agents/${KEY}/status`, body: {} },
    ]);
    renderWith(<EspecificacoesOrgTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText(/Nome da organização/), { target: { value: "Org Sintética" } });
    fireEvent.click(screen.getByTestId("specs-org-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ valores: { nome_org: "Org Sintética", regioes: "região sintética" } });
    await waitFor(() => expect(net.calls.filter((c) => c.method === "GET" && c.path === P).length).toBeGreaterThanOrEqual(2));
  });

  it("shows spec_conflita_com_regra_fixa inline on the offending field with the locked-block label", async () => {
    installFetch([
      { method: "GET", path: P, body: SPECS },
      {
        method: "PUT",
        path: P,
        status: 422,
        body: { detail: "regioes: o texto contradiz uma regra fixa da plataforma (opt_out).", code: "spec_conflita_com_regra_fixa", conflitos: ["opt_out"] },
      },
    ]);
    renderWith(<EspecificacoesOrgTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText(/Regiões atendidas/), { target: { value: "outro texto" } });
    fireEvent.click(screen.getByTestId("specs-org-salvar"));
    const box = await screen.findByTestId("spec-org-erro-regioes");
    expect(box.textContent).toContain("contradiz uma regra fixa");
    expect(box.textContent).toContain("Pedido do lead para parar de receber mensagens");
    // the other field shows no error
    expect(screen.queryByTestId("spec-org-erro-nome_org")).toBeNull();
  });
});
