/** FerramentasTab / DecisoesTab / EspecificacoesTab (declared) — draft-only replace-set writes. */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { DRAFT_ID, KEY, agentDetail } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import FerramentasTab from "../FerramentasTab";
import DecisoesTab from "../DecisoesTab";
import EspecificacoesTab from "../EspecificacoesTab";

const A = `/api/studio/agents/${KEY}`;
const V = `${A}/versions/${DRAFT_ID}`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FerramentasTab", () => {
  const itens = [{ id: "f1", ferramenta: "ferramenta_um", ativo: true, descricao: "descrição sintética", parametros: { p1: "parâmetro sintético" }, obrigatoria_skill: null }];

  it("edits description, parameter label and the required skill, then PUTs the set", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${V}/ferramentas`, body: { version_id: DRAFT_ID, itens } },
      { method: "PUT", path: `${A}/draft/ferramentas`, body: { version_id: DRAFT_ID, itens } },
    ]);
    renderWith(<FerramentasTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Descrição para o modelo"), { target: { value: "nova descrição sintética" } });
    fireEvent.change(screen.getByLabelText("Descrição de p1"), { target: { value: "rótulo novo" } });
    fireEvent.change(screen.getByLabelText("Skill que precisa ser aberta antes"), { target: { value: "skill-um" } });
    fireEvent.click(screen.getByTestId("ferramentas-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({
      itens: [{ ferramenta: "ferramenta_um", ativo: true, descricao: "nova descrição sintética", parametros: { p1: "rótulo novo" }, obrigatoria_skill: "skill-um" }],
    });
  });

  it("refuses to save a tool without a description (client-side) and never calls PUT", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${V}/ferramentas`, body: { version_id: DRAFT_ID, itens } },
    ]);
    renderWith(<FerramentasTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Descrição para o modelo"), { target: { value: " " } });
    fireEvent.click(screen.getByTestId("ferramentas-salvar"));
    expect((await screen.findByTestId("conteudo-erro")).textContent).toContain("precisa de uma descrição");
    expect(net.calls.some((c) => c.method === "PUT")).toBe(false);
  });
});

describe("DecisoesTab", () => {
  const itens = [
    { id: "d1", chave: "decisao-um", titulo: "Decisão um", regra: "regra sintética", opcoes: [{ valor: "a", rotulo: "A", padrao: true }, { valor: "b", rotulo: "B", padrao: false }] },
  ];

  it("keeps exactly one default option and PUTs the set", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${V}/decisoes`, body: { version_id: DRAFT_ID, itens } },
      { method: "PUT", path: `${A}/draft/decisoes`, body: { version_id: DRAFT_ID, itens } },
    ]);
    renderWith(<DecisoesTab agentKey={KEY} />);
    fireEvent.click(await screen.findByLabelText("Padrão: b"));
    fireEvent.click(screen.getByTestId("decisoes-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    const body = net.calls.find((c) => c.method === "PUT")!.body as { itens: Array<{ opcoes: Array<{ valor: string; padrao: boolean }> }> };
    expect(body.itens[0].opcoes).toEqual([{ valor: "a", rotulo: "A", padrao: false }, { valor: "b", rotulo: "B", padrao: true }]);
  });

  it("renders the server's 422 on save", async () => {
    installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${V}/decisoes`, body: { version_id: DRAFT_ID, itens } },
      { method: "PUT", path: `${A}/draft/decisoes`, status: 422, body: { detail: "Regra acima do limite.", code: "invalid_field" } },
    ]);
    renderWith(<DecisoesTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Regra"), { target: { value: "outra regra sintética" } });
    fireEvent.click(screen.getByTestId("decisoes-salvar"));
    expect((await screen.findByTestId("conteudo-erro")).textContent).toContain("Regra acima do limite.");
  });
});

describe("EspecificacoesTab (declared)", () => {
  it("lists declared keys and saves them", async () => {
    const itens = [{ id: "s1", chave: "nome_org", rotulo: "Nome", descricao: "ajuda", tipo: "texto", obrigatoria: true, exemplo: null }];
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${V}/specs`, body: { version_id: DRAFT_ID, itens } },
      { method: "PUT", path: `${A}/draft/specs`, body: { version_id: DRAFT_ID, itens } },
    ]);
    renderWith(<EspecificacoesTab agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Rótulo"), { target: { value: "Nome da org" } });
    fireEvent.click(screen.getByTestId("especificacoes-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({
      itens: [{ chave: "nome_org", rotulo: "Nome da org", descricao: "ajuda", tipo: "texto", obrigatoria: true, exemplo: null }],
    });
  });
});
