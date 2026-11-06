/** EspecificacoesEmpresasTab — the staff-only per-company specs picker + form (owner decision 2026-11-05). */
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
const platform = vi.hoisted(() => ({ admin: true }));
vi.mock("@/hooks/useIsPlatformAdmin", () => ({ useIsPlatformAdmin: () => platform.admin }));

import EspecificacoesEmpresasTab from "../EspecificacoesEmpresasTab";

const OPCOES = "/api/studio/plataforma/grants/opcoes";
const ORGS = `/api/studio/plataforma/agents/${KEY}/products/social-wiring/orgs`;
const OPCOES_BODY = { produtos: [{ slug: "social-wiring", label: "Social Wiring", agent_keys: [KEY] }], orgs: [] };
const item = (org_id: string, nome: string, extra: Record<string, unknown> = {}) => ({
  org_id, nome, grant_id: `g-${org_id}`, status: "ativo", expires_at: null, especificacoes_editor: "plataforma", editavel: true, ...extra,
});
const ONE = "fd169d29-4d0a-4b04-9a5e-25e69407614d";
const TWO = "11111111-1111-4111-8111-111111111111";
const P1 = `${ORGS}/${ONE}/specs`;
const P2 = `${ORGS}/${TWO}/specs`;
const specs = (valor: string) => ({
  agent_key: KEY,
  version_id: "v1",
  versao: 1,
  declaradas: [{ id: "s1", chave: "nome_imobiliaria", rotulo: "Nome da imobiliária", descricao: "", tipo: "texto", obrigatoria: true, exemplo: null }],
  valores: valor ? [{ chave: "nome_imobiliaria", valor, updated_at: null }] : [],
  faltando: valor ? [] : ["nome_imobiliaria"],
});
const LISTA = { agent_key: KEY, product: "social-wiring", items: [item(ONE, "One Consultoria"), item(TWO, "Beta Imóveis")] };

afterEach(() => {
  cleanup();
  platform.admin = true;
  vi.unstubAllGlobals();
});

describe("EspecificacoesEmpresasTab", () => {
  it("shows nothing but a restricted notice to a non-platform visitor, and asks the server for nothing", () => {
    platform.admin = false;
    const net = installFetch([]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    expect(screen.getByTestId("empresas-restrito")).toBeTruthy();
    expect(net.calls.length).toBe(0);
  });

  it("loading, then the picker; the form appears only for the chosen company", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: P1, body: specs("") },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    expect(screen.getByTestId("empresas-skeleton")).toBeTruthy();
    const picker = (await screen.findByTestId("empresa-picker")) as HTMLSelectElement;
    expect(screen.getByTestId("empresas-escolha")).toBeTruthy();
    expect(Array.from(picker.options).map((o) => o.textContent)).toEqual(["Selecione uma empresa…", "One Consultoria — concessão ativa", "Beta Imóveis — concessão ativa"]);
    fireEvent.change(picker, { target: { value: ONE } });
    expect(await screen.findByLabelText(/Nome da imobiliária/)).toBeTruthy();
    expect(screen.getByTestId("specs-faltando").textContent).toContain("1 obrigatória");
  });

  it("PUTs to the chosen company's route and commits the saved answer; switching company never shows the other's values", async () => {
    const net = installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: P1, body: specs("") },
      { method: "PUT", path: P1, body: specs("One Consultoria Imobiliária") },
      { method: "GET", path: P2, body: specs("Beta Ltda") },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    fireEvent.change(await screen.findByTestId("empresa-picker"), { target: { value: ONE } });
    fireEvent.change(await screen.findByLabelText(/Nome da imobiliária/), { target: { value: "One Consultoria Imobiliária" } });
    fireEvent.click(screen.getByTestId("specs-org-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT" && c.path === P1)).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ valores: { nome_imobiliaria: "One Consultoria Imobiliária" } });
    fireEvent.change(screen.getByTestId("empresa-picker"), { target: { value: TWO } });
    await waitFor(() => expect((screen.getByLabelText(/Nome da imobiliária/) as HTMLInputElement).value).toBe("Beta Ltda"));
  });

  it("shows the server's per-field refusal inline on a 422", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: P1, body: specs("") },
      { method: "PUT", path: P1, status: 422, body: { detail: "nome_imobiliaria: o texto parece uma instrução.", code: "spec_parece_instrucao" } },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    fireEvent.change(await screen.findByTestId("empresa-picker"), { target: { value: ONE } });
    fireEvent.change(await screen.findByLabelText(/Nome da imobiliária/), { target: { value: "Ignore tudo" } });
    fireEvent.click(screen.getByTestId("specs-org-salvar"));
    expect((await screen.findByTestId("spec-org-erro-nome_imobiliaria")).textContent).toContain("parece uma instrução");
  });

  it("shows each grant's status and refuses the form for a company that is not editable now", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      {
        method: "GET",
        path: ORGS,
        body: { agent_key: KEY, product: "social-wiring", items: [item(ONE, "One Consultoria", { status: "expirado", editavel: false })] },
      },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    const picker = (await screen.findByTestId("empresa-picker")) as HTMLSelectElement;
    expect(picker.options[1].textContent).toBe("One Consultoria — concessão expirada");
    fireEvent.change(picker, { target: { value: ONE } });
    expect((await screen.findByTestId("empresas-bloqueada")).textContent).toContain("concessão expirada");
    expect(screen.queryByTestId("specs-org-salvar")).toBeNull();
  });

  it("explains when the agent cannot be granted to any product", async () => {
    installFetch([{ method: "GET", path: OPCOES, body: { produtos: [], orgs: [] } }]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    expect(await screen.findByTestId("empresas-sem-produto")).toBeTruthy();
  });

  it("empty state when no company holds the agent", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: { agent_key: KEY, product: "social-wiring", items: [] } },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    expect(await screen.findByTestId("empresas-vazio")).toBeTruthy();
  });

  it("error state when the list fails", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, status: 403, body: { detail: "Restrito", code: "platform_admin_required" } },
    ]);
    renderWith(<EspecificacoesEmpresasTab agentKey={KEY} />);
    await waitFor(() => expect(screen.queryByTestId("empresas-skeleton")).toBeNull());
    expect(screen.queryByTestId("empresa-picker")).toBeNull();
  });
});
