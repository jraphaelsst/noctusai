/** Supervisão (Maya) — maya-blocks CONTRACT §4.3/§4.4/§4.5 (fixtures shaped by the contract). */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import Supervisao from "./Supervisao";
import { diaAnterior, hojeSP } from "@/hooks/useSupervisao";
import { formatarMetrica, SEM_DADOS } from "@/components/supervisao/metricas";

const CONFIG_ON = { supervisao_ativa: true, horas_para_assumir: 24, updated_at: "2026-10-18T10:00:00Z", updated_by: "u1" };
const CONFIG_OFF = { supervisao_ativa: false, horas_para_assumir: 24, updated_at: null, updated_by: null };
const METRICAS = {
  leads_entrada: 31, tpr_n: 0, tpr_p50_s: null, tpr_p90_s: null, tpr_sem_resposta: 3, qualificados: 9,
  qualificacao_taxa: 0.2903, frios: 0, frio_taxa: 0, invalidos: 2, invalido_taxa: 0.0645, entregas_manuais: 1,
  envios_bloqueados: 2, envios_bloqueados_por_motivo: { fora_da_janela: 2 }, handoffs_humanos: 5,
  handoffs_humanos_por_motivo: null, handoffs_emitidos: 9, horas_para_assumir: 24,
  // handoffs_nao_assumidos deliberately absent → "sem dados"
};
const scorecards = (dia: string, lista: unknown[] = [{ bloco: "sdr", agent_key: "lead-imob", rubrica_versao: "sdr.v1", calculado_at: "2026-10-19T06:00:12Z", metricas: METRICAS }]) =>
  ({ dia, supervisao_ativa: true, scorecards: lista });
const handoff = (id: string, atrasado: boolean) => ({
  id, de_bloco: "sdr", para_bloco: "atendimento", gatilho: "novo_lead", status: "emitido", atrasado,
  created_at: "2026-10-18T13:02:11Z", assumido_at: null, expirado_at: null, de_agent_key: "lead-imob", para_agent_key: null,
  referencias: {}, card: { titulo: `Card ${id}`, link: `/funil?card=${id}` },
});
const BLOCOS = {
  blocos: [
    { bloco: "sdr", rotulo: "SDR (Julia)", ordem: 1 },
    { bloco: "atendimento", rotulo: "Atendimento (corretor)", ordem: 2 },
  ],
  etapas_sem_bloco: [], agentes_por_bloco: {}, supervisao_ativa: true,
};

const erro = (status: number, code: string, message: string) =>
  Object.assign(new Error(`[${status}] ${message}`), { status, body: { error: { code, message } } });

type Rotas = { config?: () => Promise<unknown>; scorecards?: (dia: string) => Promise<unknown>; handoffs?: () => Promise<unknown> };
function setup(r: Rotas = {}, url = "/supervisao") {
  api.get.mockImplementation((u: string) => {
    if (u === "/api/supervisao/config") return (r.config ?? (() => Promise.resolve(CONFIG_ON)))();
    if (u.startsWith("/api/supervisao/scorecards")) {
      const dia = new URL(u, "http://x").searchParams.get("dia")!;
      return (r.scorecards ?? ((d: string) => Promise.resolve(scorecards(d))))(dia);
    }
    if (u.startsWith("/api/supervisao/handoffs")) return (r.handoffs ?? (() => Promise.resolve({ itens: [], proximo_cursor: null })))();
    if (u === "/api/atendimento-blocos") return Promise.resolve(BLOCOS);
    return Promise.reject(new Error(`unexpected GET ${u}`));
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}><Supervisao /></MemoryRouter>
    </QueryClientProvider>,
  );
}
const chamadas = (prefix: string) => api.get.mock.calls.map(([u]) => u as string).filter((u) => u.startsWith(prefix));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-19T15:00:00Z")); // 12:00 in SP → yesterday = 2026-10-18
  Object.values(api).forEach((f) => f.mockReset());
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("SP calendar + metric formatting", () => {
  it("yesterday is computed in America/Sao_Paulo", () => {
    expect(hojeSP(new Date("2026-10-19T02:00:00Z"))).toBe("2026-10-18"); // 23:00 SP
    expect(diaAnterior("2026-03-01")).toBe("2026-02-28");
  });
  it("never turns missing data into 0", () => {
    expect(formatarMetrica("qualificacao_taxa", null)).toBe(SEM_DADOS);
    expect(formatarMetrica("tpr_p50_s", undefined)).toBe(SEM_DADOS);
    expect(formatarMetrica("handoffs_humanos_por_motivo", null)).toBe(SEM_DADOS);
    expect(formatarMetrica("frios", 0)).toBe("0");
  });
});

describe("Supervisão page", () => {
  it("explains owner-only access on 403 (member/admin) and asks nothing else", async () => {
    setup({ config: () => Promise.reject(erro(403, "FORBIDDEN", "Somente o proprietário")) });
    expect(screen.getByTestId("supervisao-skeleton")).toBeTruthy();
    expect((await screen.findByTestId("supervisao-proibido")).textContent).toContain("exclusiva do proprietário");
    expect(chamadas("/api/supervisao/scorecards")).toHaveLength(0);
    expect(chamadas("/api/supervisao/handoffs")).toHaveLength(0);
  });

  it("supervision off: explains how to start and requests no scorecards/handoffs", async () => {
    setup({ config: () => Promise.resolve(CONFIG_OFF) });
    expect((await screen.findByTestId("supervisao-desligada")).textContent).toContain(
      "Supervisão desligada — ative para a Maya começar a avaliar",
    );
    expect(chamadas("/api/supervisao/scorecards")).toHaveLength(0);
  });

  it("owner turns supervision on with a custom deadline (both fields sent)", async () => {
    api.put.mockResolvedValue({ ...CONFIG_ON, horas_para_assumir: 12 });
    setup({ config: () => Promise.resolve(CONFIG_OFF) });
    await screen.findByTestId("supervisao-config");
    expect((screen.getByTestId("config-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("config-ativa"));
    fireEvent.change(screen.getByTestId("config-horas"), { target: { value: "200" } });
    expect(screen.getByTestId("config-horas-invalida")).toBeTruthy();
    expect((screen.getByTestId("config-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("config-horas"), { target: { value: "12" } });
    fireEvent.click(screen.getByTestId("config-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/supervisao/config", { supervisao_ativa: true, horas_para_assumir: 12 }));
  });

  it("on, day not computed yet: explains instead of showing zeros", async () => {
    setup({ scorecards: (d) => Promise.resolve(scorecards(d, [])) });
    expect((await screen.findByTestId("scorecards-vazio")).textContent).toContain("Ainda não há scorecard para 18/10/2026");
    expect(chamadas("/api/supervisao/scorecards")).toEqual(["/api/supervisao/scorecards?dia=2026-10-18"]);
  });

  it("renders Julia's sdr.v1 scorecard: values, ratio detail, definitions, and 'sem dados' for missing data", async () => {
    setup();
    const card = await screen.findByTestId("scorecard-sdr");
    expect(card.textContent).toContain("SDR (Julia) · Julia (lead-imob)");
    const m = (k: string) => within(card).getByTestId(`metrica-sdr-${k}`).textContent ?? "";
    expect(m("leads_entrada")).toContain("31");
    expect(m("qualificacao_taxa")).toContain("29%");
    expect(m("qualificacao_taxa")).toContain("(9 de 31)");
    expect(m("frio_taxa")).toContain("0%"); // a real 0 stays 0
    expect(m("tpr_p50_s")).toContain("sem dados"); // null percentile
    expect(m("handoffs_humanos_por_motivo")).toContain("sem dados"); // null until S2
    expect(m("handoffs_nao_assumidos")).toContain("sem dados"); // absent key
    expect(m("envios_bloqueados_por_motivo")).toContain("fora da janela: 2");
    expect(within(card).getByLabelText(/Definição: Qualificados ÷ leads de entrada do dia/)).toBeTruthy();
  });

  it("deep-links ?dia= and keeps the previous day on screen while switching (placeholderData)", async () => {
    let liberar!: (v: unknown) => void;
    setup(
      {
        scorecards: (d) =>
          d === "2026-10-17" ? new Promise((res) => { liberar = res; }) : Promise.resolve(scorecards(d)),
      },
      "/supervisao?dia=2026-10-16",
    );
    await screen.findByTestId("scorecard-sdr");
    expect(chamadas("/api/supervisao/scorecards")).toEqual(["/api/supervisao/scorecards?dia=2026-10-16"]);
    fireEvent.change(screen.getByTestId("scorecards-dia"), { target: { value: "2026-10-17" } });
    expect(await screen.findByTestId("scorecards-refreshing")).toBeTruthy();
    expect(screen.getByTestId("scorecard-sdr")).toBeTruthy(); // not unmounted, no skeleton
    expect(screen.queryByTestId("scorecards-skeleton")).toBeNull();
    liberar(scorecards("2026-10-17", []));
    expect(await screen.findByTestId("scorecards-vazio")).toBeTruthy();
  });

  it("ignores a future ?dia= and falls back to yesterday (SP)", async () => {
    setup({}, "/supervisao?dia=2026-10-19");
    await screen.findByTestId("scorecard-sdr");
    expect(chamadas("/api/supervisao/scorecards")).toEqual(["/api/supervisao/scorecards?dia=2026-10-18"]);
  });

  it("shows a scorecards error with the server's message", async () => {
    setup({ scorecards: () => Promise.reject(erro(422, "dia_invalido", "Dia inválido.")) });
    expect((await screen.findByTestId("scorecards-erro")).textContent).toContain("Dia inválido.");
  });

  it("handoff aging: highlights the overdue ones (the 'babá' signal)", async () => {
    setup({ handoffs: () => Promise.resolve({ itens: [handoff("a", true), handoff("b", false)], proximo_cursor: null }) });
    const lista = await screen.findByTestId("handoffs-lista");
    expect(within(lista).getByTestId("handoff-a").getAttribute("data-atrasado")).toBe("true");
    expect(within(lista).getByTestId("handoff-b").getAttribute("data-atrasado")).toBe("false");
    expect(within(lista).getByTestId("handoff-a").textContent).toContain("SDR (Julia) → Atendimento (corretor)");
    expect(within(lista).getByTestId("handoff-a").textContent).toContain("Atrasado");
    expect(screen.getByTestId("handoffs-atrasados").textContent).toContain("1 handoff passou do prazo de 24 h");
    expect(chamadas("/api/supervisao/handoffs")[0]).toContain("status=emitido");
  });

  it("no pending handoffs: says so", async () => {
    setup();
    expect(await screen.findByTestId("handoffs-vazio")).toBeTruthy();
  });
});
