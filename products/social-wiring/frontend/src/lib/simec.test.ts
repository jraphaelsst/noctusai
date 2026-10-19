/** SIMEC pure helpers — formatting, honest missing values, override-layer editing, error copy. */
import { describe, expect, it } from "vitest";
import { ApiError } from "@noctusai/lib";

import {
  applyFieldEdit,
  deletePath,
  formatSimecNumber,
  restoreItem,
  sameOverrides,
  simecErrorMessage,
  unavailableNote,
  type SimecConfig,
} from "./simec";

const cfg = {
  metrics: {
    reach: { label: "Alcance", unit: "count", available: true },
    duration_s: { label: "Duração", unit: "seconds", available: false, note: "A Graph API não retorna a duração." },
  },
  indicators: { tempo_medio_duracao: { label: "Tempo médio", op: "ratio", inputs: ["duration_s", "reach"] } },
  panel: { media_tempo_medio_duracao: { label: "Média tempo", aggregate: "mean", source: "tempo_medio_duracao" } },
} as unknown as SimecConfig;

describe("formatting", () => {
  it("rates are fractions shown as percent; counts as integers", () => {
    expect(formatSimecNumber(0.0868, "ratio")).toMatch(/8,68\s?%/);
    expect(formatSimecNumber(8504.0, "count")).toBe("8.504");
  });

  it("finds the config note behind a não-disponível panel line", () => {
    expect(unavailableNote(cfg, "media_tempo_medio_duracao")).toBe("A Graph API não retorna a duração.");
    expect(unavailableNote(cfg, "reach")).toBeNull();
  });
});

describe("override layer editing", () => {
  const base = { baseline: { min_posts: 5, lookback_days: 90 } };

  it("a value equal to the layer below is not stored; a different one is", () => {
    let d = applyFieldEdit({}, base, ["baseline", "min_posts"], 8);
    expect(d).toEqual({ baseline: { min_posts: 8 } });
    d = applyFieldEdit(d, base, ["baseline", "min_posts"], 5);
    expect(d).toEqual({});
  });

  it("restaurar padrão removes only the item's paths and keeps unrelated overrides", () => {
    const draft = { baseline: { min_posts: 8, group_by: ["format"] }, windows: { "7d": { max_days: 12 } } };
    expect(restoreItem(draft, [["baseline", "min_posts"], ["baseline", "lookback_days"]])).toEqual({
      baseline: { group_by: ["format"] },
      windows: { "7d": { max_days: 12 } },
    });
    expect(deletePath({ windows: { "7d": { max_days: 12 } } }, ["windows", "7d", "max_days"])).toEqual({});
  });

  it("compares layers independent of key order", () => {
    expect(sameOverrides({ a: 1, b: { c: 2, d: 3 } }, { b: { d: 3, c: 2 }, a: 1 })).toBe(true);
    expect(sameOverrides({ a: 1 }, {})).toBe(false);
  });
});

describe("error copy (contract table)", () => {
  const err = (status: number, message?: string) =>
    new ApiError(status, message ?? "x", message ? { error: { code: "HTTP_ERROR", message } } : undefined);

  it("maps each status to its pt-BR sentence; 422 shows the server message verbatim", () => {
    expect(simecErrorMessage(err(400))).toBe("Conta inválida.");
    expect(simecErrorMessage(err(403))).toBe("A configuração do SIMEC é restrita a administradores.");
    expect(simecErrorMessage(err(404), "leitura")).toBe("Leitura não encontrada.");
    expect(simecErrorMessage(err(404), "conta")).toBe("Conta não encontrada.");
    expect(simecErrorMessage(err(422, "windows.7d: min_days 11 > max_days 10"))).toBe(
      "windows.7d: min_days 11 > max_days 10",
    );
    expect(simecErrorMessage(err(503))).toBe("SIMEC indisponível no momento.");
  });
});
