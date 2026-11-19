/** OnboardingTab — the staff-only interview console: progress per item, import -> draft, apply -> per-item report. */
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

// the chat organ has its own suite; here only WHICH conversation the tab opens matters
vi.mock("@/components/AgentChatWindow", () => ({
  AgentChatWindow: (p: { scopeId: string | null; selectedThreadId?: string | null }) => (
    <div data-testid="chat-stub">{`${p.scopeId}:${p.selectedThreadId}`}</div>
  ),
}));

import OnboardingTab from "../OnboardingTab";

const OPCOES = "/api/studio/plataforma/grants/opcoes";
const ORGS = `/api/studio/plataforma/agents/${KEY}/products/social-wiring/orgs`;
const ONE = "fd169d29-4d0a-4b04-9a5e-25e69407614d";
const BASE = `${ORGS}/${ONE}/onboarding`;
const OPCOES_BODY = { produtos: [{ slug: "social-wiring", label: "Social Wiring", agent_keys: [KEY] }], orgs: [] };
const LISTA = {
  agent_key: KEY, product: "social-wiring",
  items: [{ org_id: ONE, nome: "One Consultoria", grant_id: "g", status: "ativo", expires_at: null, especificacoes_editor: "plataforma", editavel: true }],
};
const PROGRESSO = {
  agent_key: KEY, operacoes: [], proximo_passo: "modo_avaliacao",
  itens: [
    { n: 1, bloco: "A", nivel: "R", titulo: "Nome comercial", pergunta: "Qual é o nome?", destino: "spec:nome_imobiliaria", padrao: null, quando: [], estado: "vazio" },
    { n: 37, bloco: "H", nivel: "O", titulo: "Reengajamento", pergunta: "Quando lembrar?", destino: "sw:reengajamento", padrao: "lembrete 15 min", quando: [], estado: "fora_do_agents" },
  ],
  progresso: { por_nivel: { R: { total: 1, feitos: 0 }, C: { total: 0, feitos: 0 }, O: { total: 1, feitos: 0 } }, faltando_obrigatorios: [1] },
};

afterEach(() => {
  cleanup();
  platform.admin = true;
  vi.unstubAllGlobals();
});

const open = async () => {
  fireEvent.change(await screen.findByTestId("onboarding-empresa"), { target: { value: ONE } });
  await screen.findByTestId("onboarding-entrevista");
};

describe("OnboardingTab", () => {
  it("shows only a restricted notice to a non-platform visitor and asks the server for nothing", () => {
    platform.admin = false;
    const net = installFetch([]);
    renderWith(<OnboardingTab agentKey={KEY} />);
    expect(screen.getByTestId("onboarding-restrito")).toBeTruthy();
    expect(net.calls.length).toBe(0);
  });

  it("lists the progress per item, with the default offered for an optional one", async () => {
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: BASE, body: PROGRESSO },
    ]);
    renderWith(<OnboardingTab agentKey={KEY} />);
    await open();
    expect(screen.getByTestId("onboarding-andamento").textContent).toContain("Obrigatórios: 0/1");
    expect(screen.getByTestId("onboarding-item-37").textContent).toContain("padrão: lembrete 15 min");
  });

  it("import fills the draft (flagged unconfirmed) and writes nothing; apply sends the draft and shows the per-item report", async () => {
    const net = installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: BASE, body: PROGRESSO },
      { method: "POST", path: `${BASE}/importar`, body: { preenchidas: [{ n: 1, valor: "Acme", fonte: "nome comercial", origem: "importado", confirmado: false }], nao_reconhecidas: ["solto"], conflitos: [] } },
      {
        method: "POST", path: `${BASE}/aplicar`,
        body: {
          itens: [
            { n: 1, titulo: "Nome comercial", estado: "aplicado", codigo: null, motivo: null, destino: "spec:nome_imobiliaria", rota: null, corpo: null },
            { n: 37, titulo: "Reengajamento", estado: "recusado", codigo: "canal_sw_nao_configurado", motivo: "sem canal", destino: "sw:reengajamento", rota: "PUT /api/julia/reengajamento/config", corpo: {} },
          ],
          aplicados: 1, recusados: 1, obrigatorios_faltando: [], proximo_passo: "modo_avaliacao",
        },
      },
    ]);
    renderWith(<OnboardingTab agentKey={KEY} />);
    await open();
    fireEvent.change(screen.getByTestId("onboarding-import"), { target: { value: "nome comercial: Acme\nsolto" } });
    fireEvent.click(screen.getByTestId("onboarding-importar"));
    await waitFor(() => expect((screen.getByLabelText(/1\. Nome comercial/) as HTMLInputElement).value).toBe("Acme"));
    expect(screen.getByTestId("onboarding-import-sobras").textContent).toContain("solto");
    expect(screen.getByTestId("onboarding-rascunho").textContent).toContain("nada foi salvo");
    expect(net.calls.some((c) => c.path === `${BASE}/aplicar`)).toBe(false);

    fireEvent.click(screen.getByTestId("onboarding-item-1-confirmar"));
    fireEvent.change(screen.getByLabelText(/37\. Reengajamento/), { target: { value: '{"lembrete_min": 15}' } });
    fireEvent.click(screen.getByTestId("onboarding-aplicar"));
    await screen.findByTestId("onboarding-relatorio");
    expect(net.calls.find((c) => c.path === `${BASE}/aplicar`)!.body).toEqual({ respostas: { "1": "Acme", "37": { lembrete_min: 15 } }, importados: [1], confirmados: [1] });
    expect(screen.getByTestId("relatorio-37").textContent).toContain("Recusado");
    expect(screen.getByTestId("relatorio-37").textContent).toContain("PUT /api/julia/reengajamento/config");
    expect(screen.getByTestId("onboarding-proximo").textContent).toContain("modo de avaliação");
  });

  it("starts the interview (one POST), then opens THAT conversation of the interviewer", async () => {
    const SESSAO = { id: "s1", conversation_id: "c1", criada_em: "2026-11-17T12:00:00Z", eventos: 0, resumo_apresentado: false, aplicada: false };
    let iniciada = false;
    const net = installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      { method: "GET", path: BASE, body: { ...PROGRESSO, sessao: null } },
      { method: "POST", path: `${BASE}/conversa`, status: 201, body: { sessao_id: "s1", conversation_id: "c1", agent_key: "onboarding-imob" } },
    ]);
    renderWith(<OnboardingTab agentKey={KEY} />);
    await open();
    expect(screen.queryByTestId("chat-stub")).toBeNull();
    // after the POST the progress is re-read and now carries the session
    const spy = net.spy;
    const base = spy.getMockImplementation()!;
    spy.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.pathname === BASE && (init?.method ?? "GET") === "GET" && iniciada) {
        return new Response(JSON.stringify({ ...PROGRESSO, sessao: SESSAO }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return base(input, init);
    });
    fireEvent.click(screen.getByTestId("onboarding-iniciar"));
    iniciada = true;
    await waitFor(() => expect(screen.getByTestId("chat-stub").textContent).toBe("onboarding-imob:c1"));
    expect(net.calls.filter((c) => c.method === "POST" && c.path === `${BASE}/conversa`).length).toBe(1);
    expect(screen.getByTestId("onboarding-sessao").textContent).toContain("0 registro(s)");
  });

  it("shows what the live interview says per item (folded by the server)", async () => {
    const SESSAO = { id: "s1", conversation_id: "c1", criada_em: "2026-11-17T12:00:00Z", eventos: 4, resumo_apresentado: true, aplicada: true };
    installFetch([
      { method: "GET", path: OPCOES, body: OPCOES_BODY },
      { method: "GET", path: ORGS, body: LISTA },
      {
        method: "GET", path: BASE,
        body: { ...PROGRESSO, sessao: SESSAO, itens: PROGRESSO.itens.map((i) => ({ ...i, entrevista: i.n === 1 ? "respondido" : "pendente" })) },
      },
    ]);
    renderWith(<OnboardingTab agentKey={KEY} />);
    await open();
    expect(screen.getByTestId("onboarding-item-1-entrevista").textContent).toContain("confirmado na conversa");
    expect(screen.getByTestId("onboarding-item-37-entrevista").textContent).toContain("pendente");
    expect(screen.getByTestId("onboarding-sessao").textContent).toContain("resumo apresentado");
  });
});
