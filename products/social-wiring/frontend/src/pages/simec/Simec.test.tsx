/**
 * SIMEC page — the contract's empty states (no Instagram, reconnect, no
 * readout, no content in period, demo), não-disponível cells, error copy,
 * success panel with sample sizes + config version, and the config editor
 * (admin save / restaurar padrão / read-only / 422 verbatim).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@noctusai/lib/design-system");
  return { ...actual, useIsOrgAdmin: () => h.admin };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ApiError } from "@noctusai/lib";
import Simec from "./Simec";

// ─── Fixtures (shapes from simec-api-contract.md) ───────────────────────────

const CONFIG = {
  platform: "instagram",
  version: "instagram-defaults-1.0.0",
  metrics: {
    views: { label: "Visualizações", unit: "count", available: true },
    reach: { label: "Alcance", unit: "count", available: true },
    duration_s: { label: "Duração", unit: "seconds", available: false, note: "A Graph API não retorna a duração do vídeo." },
  },
  windows: {
    "72h": { label: "72 horas", min_days: 3, max_days: 4, enabled: true },
    "7d": { label: "7 dias", min_days: 7, max_days: 10, enabled: true },
    "30d": { label: "30 dias", min_days: 30, max_days: 35, enabled: true },
  },
  indicators: {
    taxa_interacao: { label: "Interação / alcance", op: "ratio", inputs: ["views", "reach"], unit: "ratio", enabled: true },
    tempo_medio_duracao: { label: "Tempo médio", op: "ratio", inputs: ["duration_s", "views"], unit: "ratio", enabled: true },
  },
  panel: {
    conteudos_validos: { label: "Conteúdos válidos", aggregate: "count", source: "views", enabled: true },
    media_alcance: { label: "Média de alcance", aggregate: "mean", source: "reach", enabled: true },
    media_taxa_interacao: { label: "Média interação", aggregate: "mean", source: "taxa_interacao", enabled: true },
    media_tempo_medio_duracao: { label: "Média tempo de duração", aggregate: "mean", source: "tempo_medio_duracao", enabled: true },
  },
  baseline: { lookback_days: 90, min_posts: 5, group_by: ["format"], indicators: ["reach", "taxa_interacao"] },
  alerts: {
    alcance_fora_do_padrao: { indicator: "reach", method: "outside_iqr", threshold: 1.5, direction: "both", windows: [], enabled: true },
  },
  cadence: {
    reviews: { semanal: { label: "Estratégia semanal", every_days: 7 }, mensal: { label: "Revisão mensal", every_days: 30 } },
    decision_validation_days: 28,
  },
};

const cfgResp = (version: string, org: unknown = null, account: unknown = null) => ({
  platform: "instagram",
  version,
  fingerprint: "f".repeat(64),
  config: CONFIG,
  layers: { defaults: { version: "instagram-defaults-1.0.0" }, org, account },
});

const ACCOUNT = {
  account_id: "11111111-1111-1111-1111-111111111111",
  label: "monica",
  username: "monicatangerino",
  marca_id: null,
  status: "validated",
  last_synced_at: "2026-10-19T08:30:00Z",
  insights_scope_granted: true,
  latest_readout: null,
};

const cell = (value: number | null, status = "ok", n?: number) => ({ value, status, ...(n === undefined ? {} : { n }) });
const windowPanel = (count: number) => ({
  conteudos_validos: cell(count, "ok", count),
  media_alcance: count ? cell(868.14, "ok", count) : cell(null, "sem_dados", 0),
  media_taxa_interacao: count ? cell(0.0868, "ok", count) : cell(null, "sem_dados", 0),
  media_tempo_medio_duracao: cell(null, "nao_disponivel", 0),
});

const READOUT = {
  id: "r1",
  account_id: ACCOUNT.account_id,
  platform: "instagram",
  source: "instagram_snapshots",
  period_start: "2026-09-20",
  period_end: "2026-10-19",
  history_start: "2026-06-22",
  config_version: "instagram-defaults-1.0.0+org.v2",
  config_fingerprint: "a".repeat(64),
  status_counts: { ok: 1 },
  computed_by: null,
  computed_at: "2026-10-19T12:00:00Z",
  config: CONFIG,
  panel: { "72h": windowPanel(0), "7d": windowPanel(7), "30d": windowPanel(0) },
  baselines: [
    { window: "30d", group: { format: "Carrossel" }, indicator: "reach", n: 3, mean: 1984.8, median: 1970, p25: 1748, p75: 2192, sufficient: false },
  ],
  alerts: {
    fired: [
      {
        rule: "alcance_fora_do_padrao", indicator: "reach", method: "outside_iqr", threshold: 1.5, content_id: "1789",
        window: "7d", group: { format: "Foto" }, value: 1000, direction: "below", deviation: -1.52,
        baseline: { n: 10, median: 1970, p25: 1785, p75: 2303 },
      },
    ],
    not_evaluated: [{ rule: "alcance_fora_do_padrao", window: "30d", group: { format: "Foto" }, reason: "baseline_insuficiente", baseline_n: 2 }],
  },
  readings: [
    {
      content_id: "1789", window: "7d", published_on: "2026-09-22", collected_on: "2026-09-29", format: "Foto",
      topic: "Um post", status: "ok", age_days: 7,
      metrics: { views: cell(1215), duration_s: cell(null, "nao_disponivel") },
      indicators: { taxa_interacao: cell(0.0841), tempo_medio_duracao: cell(null, "nao_disponivel") },
      source_ref: { permalink: "https://www.instagram.com/p/x" },
    },
  ],
};

// ─── Harness ────────────────────────────────────────────────────────────────

type Routes = Record<string, unknown | (() => unknown)>;
function routeGet(routes: Routes) {
  api.get.mockImplementation(async (url: string) => {
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.startsWith(k));
    if (!key) throw new Error(`unrouted GET ${url}`);
    const v = routes[key];
    const out = typeof v === "function" ? (v as () => unknown)() : v;
    if (out instanceof Error) throw out;
    return out;
  });
}

const baseRoutes = (over: Routes = {}): Routes => ({
  "/api/simec/accounts/": { items: [] },
  "/api/simec/config/defaults": cfgResp("instagram-defaults-1.0.0"),
  "/api/simec/config?platform=instagram&account_id": cfgResp("instagram-defaults-1.0.0+org.v2", { version: 2, overrides: { baseline: { min_posts: 8 } } }, null),
  "/api/simec/config?platform=instagram": cfgResp("instagram-defaults-1.0.0+org.v2", { version: 2, overrides: { baseline: { min_posts: 8 } } }),
  "/api/simec/accounts": { metrics_source: "instagram_snapshots", accounts: [ACCOUNT] },
  [`/api/simec/accounts/${ACCOUNT.account_id}/readouts/latest`]: { readout: READOUT },
  [`/api/simec/accounts/${ACCOUNT.account_id}/readouts?`]: { items: [] },
  ...over,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Simec />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  h.admin = true;
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  api.get.mockReset();
  api.post.mockReset();
  api.put.mockReset();
});

// ─── Leitura ────────────────────────────────────────────────────────────────

describe("SIMEC — empty and error states", () => {
  it("no Instagram connected: explains what to do and links to the connection + Instagram page", async () => {
    routeGet(baseRoutes({ "/api/simec/accounts": { metrics_source: "instagram_snapshots", accounts: [] } }));
    renderPage();
    const card = await screen.findByTestId("simec-no-instagram");
    expect(card.textContent).toMatch(/Conecte o Instagram desta conta para usar o SIMEC/);
    expect(screen.getByTestId("simec-connect-link").getAttribute("href")).toBe("/marcas");
    expect(screen.getByTestId("simec-instagram-page-link").getAttribute("href")).toBe("/meta");
    expect(screen.queryByTestId("simec-demo-banner")).toBeNull();
  });

  it("shows the skeleton (not the empty state) while accounts load", async () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId("simec-accounts-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("simec-no-instagram")).toBeNull();
  });

  it("an accounts failure is an error, never the empty state (503 copy)", async () => {
    routeGet(baseRoutes({ "/api/simec/accounts": () => new ApiError(503, "x", { error: { code: "INTERNAL_ERROR", message: "x" } }) }));
    renderPage();
    expect(await screen.findByText("SIMEC indisponível no momento.")).toBeTruthy();
    expect(screen.queryByTestId("simec-no-instagram")).toBeNull();
  });

  it("reconnect banner when the account lacks the insights scope", async () => {
    routeGet(baseRoutes({ "/api/simec/accounts": { metrics_source: "instagram_snapshots", accounts: [{ ...ACCOUNT, insights_scope_granted: false }] } }));
    renderPage();
    expect(await screen.findByTestId("simec-reconnect")).toBeTruthy();
    expect(screen.getByTestId("simec-reconnect-button").textContent).toMatch(/Reconectar Instagram/);
  });

  it("no readout yet: 'Nenhuma leitura ainda' + Gerar leitura POSTs and renders the result", async () => {
    routeGet(baseRoutes({ [`/api/simec/accounts/${ACCOUNT.account_id}/readouts/latest`]: { readout: null } }));
    api.post.mockResolvedValue(READOUT);
    renderPage();
    expect(await screen.findByTestId("simec-no-readout")).toBeTruthy();
    fireEvent.click(screen.getByTestId("simec-generate-empty"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`/api/simec/accounts/${ACCOUNT.account_id}/readouts`, { cadence: "mensal" }),
    );
    expect(await screen.findByTestId("simec-panel")).toBeTruthy();
  });

  it("a period with no content says so instead of showing a zero panel", async () => {
    const empty = { ...READOUT, readings: [], panel: { "72h": windowPanel(0), "7d": windowPanel(0), "30d": windowPanel(0) } };
    routeGet(baseRoutes({ [`/api/simec/accounts/${ACCOUNT.account_id}/readouts/latest`]: { readout: empty } }));
    renderPage();
    expect((await screen.findByTestId("simec-readout-empty")).textContent).toMatch(/Nenhuma publicação no período/);
    expect(screen.queryByTestId("simec-panel")).toBeNull();
  });

  it("demo data: persistent banner when the source is fake", async () => {
    routeGet(baseRoutes({ "/api/simec/accounts": { metrics_source: "fake", accounts: [ACCOUNT] } }));
    renderPage();
    expect((await screen.findAllByTestId("simec-demo-banner")).length).toBeGreaterThan(0);
  });

  it("a readout generation 422 shows the server message verbatim", async () => {
    routeGet(baseRoutes({ [`/api/simec/accounts/${ACCOUNT.account_id}/readouts/latest`]: { readout: null } }));
    api.post.mockRejectedValue(new ApiError(422, "x", { error: { code: "HTTP_ERROR", message: "cadence desconhecida: anual" } }));
    renderPage();
    fireEvent.click(await screen.findByTestId("simec-generate-empty"));
    expect(await screen.findByText("cadence desconhecida: anual")).toBeTruthy();
  });
});

describe("SIMEC — success readout", () => {
  it("panel rows/columns from the readout config, n beside means, não disponível with the note, config version visible", async () => {
    routeGet(baseRoutes());
    renderPage();
    const panel = await screen.findByTestId("simec-panel");
    const head = within(panel).getAllByRole("columnheader").map((c) => c.textContent);
    expect(head).toEqual(["Indicador", "72 horas", "7 dias", "30 dias"]);

    const row = screen.getByTestId("simec-panel-row-media_taxa_interacao");
    expect(row.textContent).toMatch(/8,68\s?%/);
    expect(row.textContent).toMatch(/n=7/);
    // A window with no valid reading is "sem dados", never 0.
    expect(within(row).getAllByTestId("simec-cell-sem-dados").length).toBe(2);

    const tempo = screen.getByTestId("simec-panel-row-media_tempo_medio_duracao");
    const nd = within(tempo).getAllByTestId("simec-cell-nao-disponivel");
    expect(nd).toHaveLength(3);
    expect(nd[0].textContent).toBe("não disponível");
    expect(nd[0].getAttribute("title")).toBe("A Graph API não retorna a duração do vídeo.");
    expect(tempo.textContent).not.toMatch(/\b0\b/);

    expect(screen.getByTestId("simec-readout-config-version").textContent).toMatch(/instagram-defaults-1\.0\.0\+org\.v2/);
  });

  it("alerts are worded relative to the profile's history; not-evaluated + insufficient baselines are shown", async () => {
    routeGet(baseRoutes());
    renderPage();
    const alert = await screen.findByTestId("simec-alert-fired");
    expect(alert.textContent).toMatch(/abaixo do padrão do perfil/);
    expect(screen.getByTestId("simec-alerts-not-evaluated").textContent).toMatch(/amostra insuficiente/);
    expect(screen.getByTestId("simec-baseline-insuficiente")).toBeTruthy();
  });
});

// ─── Configuração ───────────────────────────────────────────────────────────

describe("SIMEC — config editor", () => {
  async function openConfig() {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByTestId("simec-tab-config"));
    await screen.findByTestId("simec-cfg-section-baseline");
    return user;
  }

  it("admin edits the org layer and saves the WHOLE layer (PUT /config/org)", async () => {
    routeGet(baseRoutes());
    api.put.mockResolvedValue(cfgResp("instagram-defaults-1.0.0+org.v3", { version: 3, overrides: {} }));
    await openConfig();
    // Existing org override is marked and its value shown.
    expect(screen.getByTestId("simec-cfg-overridden-baseline")).toBeTruthy();
    expect((screen.getByLabelText("Amostra mínima (posts)") as HTMLInputElement).value).toBe("8");

    fireEvent.change(screen.getByLabelText("Dias de histórico"), { target: { value: "60" } });
    fireEvent.click(screen.getByTestId("simec-cfg-save"));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/api/simec/config/org", {
        platform: "instagram",
        overrides: { baseline: { min_posts: 8, lookback_days: 60 } },
      }),
    );
  });

  it("restaurar padrão drops the item's override; saving sends the reduced layer", async () => {
    routeGet(baseRoutes());
    api.put.mockResolvedValue(cfgResp("instagram-defaults-1.0.0", { version: 3, overrides: {} }));
    await openConfig();
    fireEvent.click(screen.getByTestId("simec-cfg-restore-baseline"));
    expect((screen.getByLabelText("Amostra mínima (posts)") as HTMLInputElement).value).toBe("5");
    expect(screen.queryByTestId("simec-cfg-overridden-baseline")).toBeNull();
    fireEvent.click(screen.getByTestId("simec-cfg-save"));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/api/simec/config/org", { platform: "instagram", overrides: {} }),
    );
  });

  it("profile layer PUTs to the account endpoint", async () => {
    routeGet(baseRoutes());
    api.put.mockResolvedValue(cfgResp("v", { version: 2, overrides: {} }, { version: 1, overrides: {} }));
    const user = await openConfig();
    await user.click(screen.getByTestId("simec-cfg-layer-perfil"));
    const box = await screen.findByLabelText("Calcular", { selector: "#simec-cfg-indicators-tempo_medio_duracao-enabled" });
    fireEvent.click(box);
    fireEvent.click(screen.getByTestId("simec-cfg-save"));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(`/api/simec/accounts/${ACCOUNT.account_id}/config`, {
        platform: "instagram",
        overrides: { indicators: { tempo_medio_duracao: { enabled: false } } },
      }),
    );
  });

  it("a 422 from the server is shown verbatim (names the field)", async () => {
    routeGet(baseRoutes());
    api.put.mockRejectedValue(new ApiError(422, "x", { error: { code: "HTTP_ERROR", message: "windows.7d: min_days 11 > max_days 10" } }));
    await openConfig();
    fireEvent.change(screen.getByLabelText("Dia mínimo", { selector: "#simec-cfg-windows-7d-min_days" }), { target: { value: "11" } });
    fireEvent.click(screen.getByTestId("simec-cfg-save"));
    expect(await screen.findByText("windows.7d: min_days 11 > max_days 10")).toBeTruthy();
  });

  it("non-admins see the config read-only (no save, inputs disabled)", async () => {
    h.admin = false;
    routeGet(baseRoutes());
    await openConfig();
    expect(screen.getByTestId("simec-cfg-readonly")).toBeTruthy();
    expect(screen.queryByTestId("simec-cfg-save")).toBeNull();
    expect(screen.queryByTestId("simec-cfg-restore-baseline")).toBeNull();
    expect((screen.getByLabelText("Dias de histórico") as HTMLInputElement).disabled).toBe(true);
  });
});
