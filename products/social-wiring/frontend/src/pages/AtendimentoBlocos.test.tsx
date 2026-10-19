/** Blocos do atendimento — maya-blocks CONTRACT §4.1/§4.2. Fixtures use the real wire shape
 * (`{data: …}` success envelope, `{error: {code, message}}` refusals — backend tests/modules/atendimento_blocos). */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import AtendimentoBlocos from "./AtendimentoBlocos";

const bloco = (b: string, rotulo: string, ordem: number, pipeline: string | null, etapas: string[], agent_key: string | null = null) => ({
  bloco: b, rotulo, ordem, agent_key, ativo: false, pipeline, etapas, origem: "padrao", updated_at: null, updated_by: null,
});
const CFG = {
  blocos: [
    bloco("sdr", "SDR (Julia)", 1, null, [], "julia"),
    bloco("atendimento", "Atendimento (corretor)", 2, "funil", ["qualificacao", "visitas", "proposta_recebida"]),
    bloco("negociacao", "Negociação", 3, "funil", ["negociacao", "proposta_decisao"]),
    bloco("juridico", "Jurídico", 4, "processos_venda", ["elaboracao_contrato", "analise_partes", "revisao_contrato", "assinatura"]),
    bloco("financeiro", "Financeiro", 5, "processos_venda", ["financiamento_escritura", "finalizacao", "entrega_chaves"]),
    bloco("contador", "Contador", 6, "processos_venda", ["nota_fiscal"]),
  ],
  etapas_sem_bloco: [{ pipeline: "funil", slug: "pos_venda", label: "Pós-venda" }],
  agentes_por_bloco: { sdr: ["julia"] },
  supervisao_ativa: false,
};
const stage = (slug: string, label: string) => ({ id: slug, slug, label, cor: "blue", posicao: 0, papel: null, ativo: true });
const FUNIL = [
  stage("qualificacao", "Qualificação"), stage("visitas", "Visitas"), stage("proposta_recebida", "Proposta Recebida"),
  stage("negociacao", "Negociação"), stage("proposta_decisao", "Proposta Aceita/Rejeitada"), stage("pos_venda", "Pós-venda"),
];

const erro = (status: number, code: string, message: string) =>
  Object.assign(new Error(`[${status}] ${message}`), { status, body: { error: { code, message } } });

function setup(get: (url: string) => Promise<unknown> = defaultGet) {
  api.get.mockImplementation(get);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><AtendimentoBlocos /></QueryClientProvider>);
}
function defaultGet(url: string): Promise<unknown> {
  if (url === "/api/atendimento-blocos") return Promise.resolve({ data: CFG });
  if (url === "/api/funil/etapas") return Promise.resolve({ data: FUNIL });
  if (url === "/api/processos-venda/etapas") return Promise.resolve({ data: [] });
  return Promise.reject(new Error(`unexpected GET ${url}`));
}

beforeEach(() => { h.admin = true; Object.values(api).forEach((f) => f.mockReset()); });
afterEach(cleanup);

describe("Blocos do atendimento", () => {
  it("shows a skeleton, then the 6 blocks, stage labels, the unowned stages and the supervision-off note", async () => {
    setup();
    expect(screen.getByTestId("blocos-skeleton")).toBeTruthy();
    const tabela = await screen.findByTestId("blocos-tabela");
    expect(within(tabela).getAllByRole("row")).toHaveLength(7); // header + 6
    expect(within(screen.getByTestId("bloco-sdr")).getByText("Julia (julia)")).toBeTruthy();
    expect(await within(screen.getByTestId("bloco-atendimento")).findByText("Qualificação")).toBeTruthy();
    expect(screen.getByTestId("etapas-sem-bloco").textContent).toContain("Pós-venda · Funil de Vendas");
    expect(screen.getByTestId("blocos-supervisao-off")).toBeTruthy();
  });

  it("is read-only for members: no edit button, a read-only note", async () => {
    h.admin = false;
    setup();
    await screen.findByTestId("blocos-tabela");
    expect(screen.getByTestId("blocos-readonly")).toBeTruthy();
    expect(screen.queryByTestId("blocos-editar")).toBeNull();
    expect(screen.queryByTestId("ativo-atendimento")).toBeNull();
  });

  it("saves only the changed blocks (partial PUT, no pipeline) and leaves edit mode", async () => {
    const depois = { ...CFG, blocos: CFG.blocos.map((b) => (b.bloco === "atendimento" ? { ...b, ativo: true, origem: "org", etapas: ["qualificacao", "visitas", "proposta_recebida", "pos_venda"] } : b)) };
    api.put.mockResolvedValue({ data: depois });
    setup();
    fireEvent.click(await screen.findByTestId("blocos-editar"));
    expect((screen.getByTestId("blocos-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("ativo-atendimento"));
    fireEvent.click(screen.getByTestId("etapas-atendimento"));
    fireEvent.click(await screen.findByTestId("etapas-atendimento-option-pos_venda"));
    fireEvent.click(screen.getByTestId("blocos-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put).toHaveBeenCalledWith("/api/atendimento-blocos", {
      blocos: [{ bloco: "atendimento", agent_key: null, ativo: true, etapas: ["qualificacao", "visitas", "proposta_recebida", "pos_venda"] }],
    });
    await waitFor(() => expect(screen.queryByTestId("blocos-salvar")).toBeNull());
    expect(within(screen.getByTestId("bloco-atendimento")).getByText("Sim")).toBeTruthy();
  });

  it("hints which block owns a stage, and shows the server's overlap refusal verbatim", async () => {
    api.put.mockRejectedValue(erro(422, "etapa_em_dois_blocos", "A etapa “negociacao” ficaria em dois blocos: Atendimento (corretor) e Negociação."));
    setup();
    fireEvent.click(await screen.findByTestId("blocos-editar"));
    fireEvent.click(screen.getByTestId("etapas-atendimento"));
    const opt = await screen.findByTestId("etapas-atendimento-option-negociacao");
    expect(opt.textContent).toContain("Negociação (em Negociação)");
    fireEvent.click(opt);
    fireEvent.click(screen.getByTestId("blocos-salvar"));
    const alerta = await screen.findByTestId("blocos-erro");
    expect(alerta.getAttribute("role")).toBe("alert");
    expect(alerta.textContent).toContain("ficaria em dois blocos: Atendimento (corretor) e Negociação");
    expect(screen.getByTestId("blocos-salvar")).toBeTruthy(); // still editing, draft kept
  });

  it("on a concurrent save, explains and re-reads the config", async () => {
    api.put.mockRejectedValue(erro(409, "conflito_concorrente", "conflito"));
    setup();
    fireEvent.click(await screen.findByTestId("blocos-editar"));
    fireEvent.click(screen.getByTestId("ativo-contador"));
    const antes = api.get.mock.calls.filter(([u]) => u === "/api/atendimento-blocos").length;
    fireEvent.click(screen.getByTestId("blocos-salvar"));
    expect((await screen.findByTestId("blocos-erro")).textContent).toContain("Outra pessoa salvou");
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([u]) => u === "/api/atendimento-blocos").length).toBeGreaterThan(antes),
    );
  });

  it("shows a load error with retry", async () => {
    setup((url) => (url === "/api/atendimento-blocos" ? Promise.reject(new Error("boom")) : defaultGet(url)));
    expect(await screen.findByTestId("blocos-erro-carregar")).toBeTruthy();
  });
});
