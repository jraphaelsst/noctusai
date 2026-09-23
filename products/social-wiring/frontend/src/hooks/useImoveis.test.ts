/**
 * useImoveis — display-helper tests, plus `useImovel`'s 404-does-not-retry
 * contract (Bug A: a manually-registered código's mirror 404 is a STABLE
 * state, retrying it three times just stretches the skeleton for an answer
 * that will not change) and its global-toast opt-out (a stable "not found"
 * state shouldn't also surface an "Erro ao carregar dados" toast — see
 * `query-client.test.ts` for the suppression mechanism itself).
 *
 * The display helpers are covered against the pure functions directly (no
 * TanStack wiring needed); the retry/meta contracts mock
 * `@tanstack/react-query` to capture the options object `useQuery` receives,
 * same convention `useMatriculas.test.ts`/`useN8nWorkflows.test.ts` use — no
 * QueryClientProvider needed to inspect a `retry` function's own logic.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  caracteristicaLabel,
  caracteristicasAusentes,
  formatBool,
  formatCount,
  formatMetros,
} from "./useImoveis";

// ─── Amenity labels — CONTRACT § 3's missing-key list ──────────────────────

describe("caracteristicaLabel — CONTRACT § 3 missing keys", () => {
  const casos: [string, string][] = [
    ["cercaeletrica", "Cerca elétrica"],
    ["alarme", "Alarme"],
    ["antenaparabolica", "Antena parabólica"],
    ["aquecimentoeletrico", "Aquecimento elétrico"],
    ["calefacao", "Calefação"],
    ["porao", "Porão"],
    ["sotao", "Sótão"],
    ["patio", "Pátio"],
    ["gabinete", "Gabinete"],
    ["sala", "Sala"],
    ["salaestar", "Sala de estar"],
    ["estarintimo", "Estar íntimo"],
    ["banheiroauxiliar", "Banheiro auxiliar"],
    ["cozinhamontada", "Cozinha montada"],
    ["cozinhacomtanque", "Cozinha com tanque"],
    ["construcaoalvenaria", "Construção em alvenaria"],
    ["living", "Living"],
  ];

  it.each(casos)("labels %s as %s", (slug, esperado) => {
    expect(caracteristicaLabel(slug)).toBe(esperado);
  });

  it("still resolves the upstream-typo collision key (already covered pre-correction)", () => {
    // Backend merges "Dependenciade Empregada" (typo) and
    // "Dependencia De Empregada" into ONE slug via CARACTERISTICA_COLLISIONS
    // — both fold to the same value, so there is only one key to assert.
    expect(caracteristicaLabel("dependenciadeempregada")).toBe("Dependência de empregada");
  });

  it("still falls back gracefully for a genuinely unknown slug", () => {
    expect(caracteristicaLabel("umaAmenidadeNovaDoVista")).toBe("Uma Amenidade Nova Do Vista");
  });
});

// ─── The 0-vs-null distinction ──────────────────────────────────────────────

describe("formatCount — genuine 0 vs unknown", () => {
  it("renders a real 0 as '0', not '—'", () => {
    expect(formatCount(0)).toBe("0");
  });

  it("renders null as '—'", () => {
    expect(formatCount(null)).toBe("—");
  });

  it("renders a positive count normally", () => {
    expect(formatCount(3)).toBe("3");
  });
});

describe("formatBool — Sim/Não, never true/false, null hides the field", () => {
  it("renders true as 'Sim'", () => {
    expect(formatBool(true)).toBe("Sim");
  });

  it("renders false as 'Não' — a real false is a fact, not absence", () => {
    expect(formatBool(false)).toBe("Não");
  });

  it("renders null as null, not '—' — CONTRACT § 7: null hides the field", () => {
    expect(formatBool(null)).toBeNull();
  });
});

describe("formatMetros — linear measurement, distinct unit from formatArea", () => {
  it("appends 'm', not 'm²'", () => {
    expect(formatMetros(12)).toBe("12 m");
  });

  it("renders null as '—'", () => {
    expect(formatMetros(null)).toBe("—");
  });
});

// ─── caracteristicasAusentes — the "não possui" complement ─────────────────

describe("caracteristicasAusentes", () => {
  it("excludes present slugs and only returns known ones", () => {
    const presentes = ["piscina", "sauna"];
    const ausentes = caracteristicasAusentes(presentes);

    expect(ausentes).not.toContain("piscina");
    expect(ausentes).not.toContain("sauna");
    expect(ausentes).toContain("alarme");
    expect(ausentes).toContain("living");
  });

  it("returns every known slug when nothing is present", () => {
    const ausentes = caracteristicasAusentes([]);
    expect(ausentes.length).toBeGreaterThan(60);
  });

  it("is case-insensitive against the present list", () => {
    const ausentes = caracteristicasAusentes(["PISCINA"]);
    expect(ausentes).not.toContain("piscina");
  });
});

// ─── useImovel — Bug A: a 404 on the Vista mirror never retries ────────────

describe("useImovel — 404 does not retry, and does not toast", () => {
  it("does not retry a 404 — a manually-registered código's stable mirror-miss", async () => {
    const capturedOptions: Array<{
      retry?: (failureCount: number, error: unknown) => boolean;
      meta?: { suppressErrorToastStatuses?: number[] };
    }> = [];
    vi.doMock("@noctusai/seed/infra", () => ({
      api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
    }));
    vi.doMock("@tanstack/react-query", () => ({
      useQuery: (opts: (typeof capturedOptions)[number]) => {
        capturedOptions.push(opts);
        return { data: undefined, isPending: false, isError: false };
      },
      useMutation: () => ({ mutate: vi.fn(), isPending: false }),
      useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    }));
    vi.resetModules();
    const { useImovel } = await import("./useImoveis");
    const { ApiError } = await import("@noctusai/lib");

    useImovel("AP1234");
    const { retry, meta } = capturedOptions[capturedOptions.length - 1];

    expect(retry?.(0, new ApiError(404, "não encontrado"))).toBe(false);
    expect(retry?.(2, new ApiError(404, "não encontrado"))).toBe(false);

    // Any other status still gets react-query's normal (default 3) retry —
    // only a 404 is treated as a stable, non-transient state.
    expect(retry?.(0, new ApiError(500, "erro"))).toBe(true);
    expect(retry?.(2, new ApiError(500, "erro"))).toBe(true);
    expect(retry?.(3, new ApiError(500, "erro"))).toBe(false);

    // A non-ApiError failure (network drop, `safeFetch`'s own throw shape)
    // also keeps the default retry — the 404 carve-out is specific to a
    // real HTTP 404, never a blanket "stop retrying on any error".
    expect(retry?.(0, new Error("network"))).toBe(true);

    // Bug 1: the same 404 also opts out of the global error toast
    // (`query-client.ts`'s `suppressErrorToastStatuses`) — a genuinely
    // unsynced manual código is not something the user needs an "Erro ao
    // carregar dados" toast about.
    expect(meta?.suppressErrorToastStatuses).toEqual([404]);

    vi.doUnmock("@noctusai/seed/infra");
    vi.doUnmock("@tanstack/react-query");
    vi.resetModules();
  });
});

describe("useImovelRegistro — genuinely unknown código does not toast either", () => {
  it("carries the same 404 toast opt-out as useImovel", async () => {
    const capturedOptions: Array<{ meta?: { suppressErrorToastStatuses?: number[] } }> = [];
    vi.doMock("@noctusai/seed/infra", () => ({
      api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
    }));
    vi.doMock("@tanstack/react-query", () => ({
      useQuery: (opts: (typeof capturedOptions)[number]) => {
        capturedOptions.push(opts);
        return { data: undefined, isPending: false, isError: false };
      },
      useMutation: () => ({ mutate: vi.fn(), isPending: false }),
      useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    }));
    vi.resetModules();
    const { useImovelRegistro } = await import("./useImoveis");

    useImovelRegistro("AP1234");
    const { meta } = capturedOptions[capturedOptions.length - 1];

    expect(meta?.suppressErrorToastStatuses).toEqual([404]);

    vi.doUnmock("@noctusai/seed/infra");
    vi.doUnmock("@tanstack/react-query");
    vi.resetModules();
  });
});
