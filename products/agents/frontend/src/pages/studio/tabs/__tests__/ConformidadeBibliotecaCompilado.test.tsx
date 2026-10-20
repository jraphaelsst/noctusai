/** Conformidade (honest unavailable state), Biblioteca (pins + "nova versão"), Compilado (cache marker + off-prompt rows). */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { ACTIVE_ID, DRAFT_ID, KEY, agentDetail } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import ConformidadeTab from "../ConformidadeTab";
import BibliotecaTab from "../BibliotecaTab";
import CompiladoJuliaTab, { splitManifest } from "../CompiladoJuliaTab";

const A = `/api/studio/agents/${KEY}`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ConformidadeTab", () => {
  it("says the API is unavailable instead of faking data when the route is absent", async () => {
    installFetch([
      { method: "GET", path: `${A}/conformidade/regras`, status: 404, body: { detail: "Not Found" } },
      { method: "GET", path: `${A}/conformidade/violacoes`, status: 404, body: { detail: "Not Found" } },
    ]);
    renderWith(<ConformidadeTab agentKey={KEY} />);
    expect(await screen.findByText(/API de conformidade ainda não está disponível/)).toBeTruthy();
  });

  it("toggles a rule and lists violations when the API exists", async () => {
    const net = installFetch([
      { method: "GET", path: `${A}/conformidade/regras`, body: { items: [{ regra: "regra_a", ativo: true, politica: "registrar", mensagem_correcao_texto_chave: null }] } },
      { method: "GET", path: `${A}/conformidade/violacoes`, body: { items: [{ id: "v1", regra: "regra_a", politica: "registrar", bloqueada: false, thread_id: null, created_at: "2026-10-10T10:00:00Z" }] } },
      { method: "PUT", path: `${A}/conformidade/regras/regra_a`, body: { regra: "regra_a", ativo: false, politica: "registrar", mensagem_correcao_texto_chave: null } },
    ]);
    renderWith(<ConformidadeTab agentKey={KEY} />);
    fireEvent.click(await screen.findByLabelText("Ativar regra_a"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ ativo: false });
    expect(screen.getByTestId("violacoes-tabela").textContent).toContain("regra_a");
  });
});

describe("BibliotecaTab", () => {
  const pins = {
    version_id: DRAFT_ID,
    items: [{ skill: "skill-um", skill_versao_id: "sv1", versao: 1, obrigatoria_para: [], ordem: 0, nova_versao: 2, nova_versao_id: "sv2" }],
  };
  const common = [
    { method: "GET" as const, path: A, body: agentDetail() },
    { method: "GET" as const, path: `${A}/versions/${DRAFT_ID}/skills-biblioteca`, body: pins },
    { method: "GET" as const, path: `${A}/versions/${DRAFT_ID}/ferramentas`, body: { version_id: DRAFT_ID, itens: [{ id: "f1", ferramenta: "ferramenta_um", ativo: true, descricao: "d", parametros: {}, obrigatoria_skill: null }] } },
    { method: "GET" as const, path: "/api/skills-biblioteca", body: { items: [{ id: "s1", chave: "skill-um", nome: "Skill Um", descricao: null, versao_publicada: 2, tem_rascunho: false }] } },
  ];

  it("flags a newer library version and re-pins it keeping the required tools", async () => {
    const net = installFetch([
      ...common,
      { method: "PUT", path: `${A}/draft/skills-biblioteca/skill-um`, body: { ...pins, items: [{ ...pins.items[0], versao: 2, nova_versao: null }] } },
    ]);
    renderWith(<BibliotecaTab agentKey={KEY} />);
    expect((await screen.findByTestId("pino-nova-skill-um")).textContent).toContain("v2");
    fireEvent.click(screen.getByTestId("pino-atualizar-skill-um"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ versao: 2, obrigatoria_para: [], ordem: 0 });
  });

  it("sets obrigatoria_para from the version's tools", async () => {
    const net = installFetch([
      ...common,
      { method: "PUT", path: `${A}/draft/skills-biblioteca/skill-um`, body: pins },
    ]);
    renderWith(<BibliotecaTab agentKey={KEY} />);
    fireEvent.click(await screen.findByLabelText("ferramenta_um"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect((net.calls.find((c) => c.method === "PUT")!.body as { obrigatoria_para: string[] }).obrigatoria_para).toEqual(["ferramenta_um"]);
  });
});

describe("CompiladoJuliaTab", () => {
  const texto = "BLOCO-A\n\nBLOCO-B\n\nCLIENTE";
  const manifest = [
    { chave: "a", titulo: "A", origem: { tipo: "secao", id: "s1", campo: null }, inicio: 0, fim: 7, chars: 7, tokens: 2 },
    { chave: "b", titulo: "B", origem: { tipo: "secao", id: "s2", campo: null }, inicio: 9, fim: 16, chars: 7, tokens: 2 },
    { chave: "c", titulo: "Cliente em foco: Y", origem: { tipo: "auto", id: null, campo: "cliente" }, inicio: 18, fim: 25, chars: 7, tokens: 2 },
    { chave: "texto:grupo.um", titulo: "grupo.um", origem: { tipo: "texto", id: "t1", campo: "conteudo" }, inicio: null, fim: null, chars: 12, tokens: 3 },
    { chave: "ferramenta:ferramenta_um", titulo: "ferramenta_um", origem: { tipo: "ferramenta", id: "f1", campo: "descricao" }, inicio: null, fim: null, chars: 9, tokens: 3 },
  ];

  it("splits in-prompt from off-prompt rows and puts the cache breakpoint before the client layer", () => {
    const r = splitManifest(manifest);
    expect(r.dentro).toHaveLength(3);
    expect(r.fora.map((m) => m.chave)).toEqual(["texto:grupo.um", "ferramenta:ferramenta_um"]);
    expect(r.pontoCache).toBe(16);
  });

  it("renders the payload with a cache marker, the off-prompt list and the per-org view", async () => {
    installFetch([
      { method: "GET", path: A, body: agentDetail() },
      {
        method: "GET",
        path: `${A}/versions/${DRAFT_ID}/payload`,
        body: { version_id: DRAFT_ID, hash: "sha256:abcdef0123456789", texto, tokens_estimados: 7, manifest, avisos: [], textos: [], ferramentas: [], decisoes: [], specs: [] },
      },
      {
        method: "GET",
        path: `${A}/compilado`,
        body: { version_id: ACTIVE_ID, versao: 1, hash: "sha256:0123456789abcdef", texto, tokens_estimados: 7, manifest, avisos: [], specs_faltando: ["nome_org"], completo: false },
      },
    ]);
    renderWith(<CompiladoJuliaTab agentKey={KEY} />);
    expect((await screen.findAllByTestId("compiled-cache-breakpoint")).length).toBeGreaterThanOrEqual(1);
    await waitFor(() => expect(screen.getAllByTestId("compilado-fora")).toHaveLength(2)); // definition + per-org
    expect(screen.getAllByTestId("fora-texto:grupo.um").length).toBe(2);
    expect(screen.getByText(/Faltam especificações: nome_org/)).toBeTruthy();
  });
});
