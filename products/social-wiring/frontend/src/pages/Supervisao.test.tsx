/** Supervisão (Maya) — maya-blocks CONTRACT §4.3/§4.4/§4.5. Fixtures use the real wire shape
 * (`{data: …}` envelope, 403 `exclusivo_proprietario` — backend tests/modules/supervisao/test_router.py). */
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
  tpr_humano_n: 2, tpr_humano_p50_s: 45, tpr_humano_p90_s: 130, respondidos_por_humano_antes_do_agente: 1,
  falhas_registro: 2, dados_incompletos: true,
  // handoffs_nao_assumidos deliberately absent → "sem dados"
};
const scorecards = (dia: string, lista: unknown[] = SC_PADRAO, ativa = true) => ({ dia, supervisao_ativa: ativa, scorecards: lista });
const SC_PADRAO: unknown[] = [{ bloco: "sdr", agent_key: "julia", rubrica_versao: "sdr.v2", calculado_at: "2026-10-19T06:00:12Z", metricas: METRICAS }];
const handoff = (id: string, atrasado: boolean) => ({
  id, de_bloco: "sdr", para_bloco: "atendimento", gatilho: "novo_lead", status: "emitido", atrasado,
  created_at: "2026-10-18T13:02:11Z", assumido_at: null, expirado_at: null, de_agent_key: "julia", para_agent_key: null,
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
  const ok = (p: Promise<unknown>) => p.then((d) => ({ data: d }));
  api.get.mockImplementation((u: string) => {
    if (u === "/api/supervisao/config") return ok((r.config ?? (() => Promise.resolve(CONFIG_ON)))());
    if (u.startsWith("/api/supervisao/scorecards")) {
      const dia = new URL(u, "http://x").searchParams.get("dia")!;
      return ok((r.scorecards ?? ((d: string) => Promise.resolve(scorecards(d))))(dia));
    }
    if (u.startsWith("/api/supervisao/handoffs")) return ok((r.handoffs ?? (() => Promise.resolve({ itens: [], proximo_cursor: null })))());
    if (u === "/api/atendimento-blocos") return ok(Promise.resolve(BLOCOS));
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
    expect(formatarMetrica("dados_incompletos", false)).toBe("Não");
    expect(formatarMetrica("dados_incompletos", null)).toBe(SEM_DADOS);
    expect(formatarMetrica("handoffs_humanos_por_motivo", null)).toBe(SEM_DADOS);
    expect(formatarMetrica("frios", 0)).toBe("0");
  });
});

describe("Supervisão page", () => {
  it("admin: owner-only parts explain `exclusivo_proprietario`, the handoff aging still shows", async () => {
    setup({
      config: () => Promise.reject(erro(403, "exclusivo_proprietario", "Supervisão: exclusiva do proprietário da organização.")),
      handoffs: () => Promise.resolve({ itens: [handoff("a", true)], proximo_cursor: null }),
    });
    expect(screen.getByTestId("supervisao-skeleton")).toBeTruthy();
    expect((await screen.findByTestId("supervisao-proibido")).textContent).toContain("exclusivos do proprietário");
    expect(chamadas("/api/supervisao/scorecards")).toHaveLength(0);
    expect((await screen.findByTestId("handoff-a")).getAttribute("data-atrasado")).toBe("true");
    expect(screen.getByTestId("handoffs-atrasados").textContent).toContain("1 handoff passou do prazo sem ninguém assumir");
    expect(screen.queryByTestId("supervisao-config")).toBeNull();
  });

  it("member: owner-only message + a generic 403 FORBIDDEN on handoffs", async () => {
    setup({
      config: () => Promise.reject(erro(403, "exclusivo_proprietario", "exclusiva do proprietário")),
      handoffs: () => Promise.reject(erro(403, "FORBIDDEN", "Forbidden")),
    });
    expect(await screen.findByTestId("supervisao-proibido")).toBeTruthy();
    expect(await screen.findByTestId("handoffs-proibido")).toBeTruthy();
  });

  it("a 403 without the owner-only code is NOT rendered as owner-only", async () => {
    setup({ config: () => Promise.reject(erro(403, "FORBIDDEN", "Acesso negado.")) });
    expect((await screen.findByTestId("supervisao-erro")).textContent).toContain("Acesso negado.");
    expect(screen.queryByTestId("supervisao-proibido")).toBeNull();
  });

  it("supervision off: history preserved — past scorecards still shown, labelled", async () => {
    setup({
      config: () => Promise.resolve(CONFIG_OFF),
      scorecards: (d) => Promise.resolve(scorecards(d, SC_PADRAO, false)),
    });
    expect((await screen.findByTestId("supervisao-desligada")).textContent).toContain("Supervisão desligada");
    expect((await screen.findByTestId("scorecards-off")).textContent).toContain("Supervisão desligada — histórico preservado");
    expect(screen.getByTestId("scorecard-sdr")).toBeTruthy();
  });

  it("supervision off and nothing stored for the day: says so", async () => {
    setup({ config: () => Promise.resolve(CONFIG_OFF), scorecards: (d) => Promise.resolve(scorecards(d, [], false)) });
    expect((await screen.findByTestId("scorecards-vazio")).textContent).toContain("Nenhum scorecard guardado para 18/10/2026");
  });

  it("owner turns supervision on with a custom deadline (both fields sent)", async () => {
    api.put.mockResolvedValue({ data: { ...CONFIG_ON, horas_para_assumir: 12 } });
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

  it("renders Julia's sdr.v2 scorecard: values, ratio detail, definitions, and 'sem dados' for missing data", async () => {
    setup();
    const card = await screen.findByTestId("scorecard-sdr");
    expect(card.textContent).toContain("SDR (Julia) · Julia (julia)");
    const m = (k: string) => within(card).getByTestId(`metrica-sdr-${k}`).textContent ?? "";
    expect(m("leads_entrada")).toContain("31");
    expect(m("qualificacao_taxa")).toContain("29%");
    expect(m("qualificacao_taxa")).toContain("(9 de 31)");
    expect(m("frio_taxa")).toContain("0%"); // a real 0 stays 0
    expect(m("tpr_p50_s")).toContain("sem dados"); // null percentile
    expect(m("handoffs_humanos_por_motivo")).toContain("sem dados"); // null until S2
    expect(m("handoffs_nao_assumidos")).toContain("sem dados"); // absent key
    expect(m("tpr_humano_p50_s")).toContain("45 s"); // a person's first reply, reported beside (never as) Julia's
    expect(m("falhas_registro")).toContain("2");
    expect(m("dados_incompletos")).toContain("Sim"); // a day with registration failures never reads complete
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
