import { describe, expect, it } from "vitest";
import { tempoDesde } from "./imobshotaiFormat";

const AGORA = Date.parse("2026-11-14T12:00:00Z");
describe("tempoDesde", () => {
  it.each([
    ["2026-11-14T11:59:40Z", "agora"],
    ["2026-11-14T11:55:00Z", "há 5 min"],
    ["2026-11-14T09:00:00Z", "há 3 h"],
    ["2026-11-13T11:00:00Z", "há 1 dia"],
    ["2026-11-11T12:00:00Z", "há 3 dias"],
  ])("%s -> %s", (iso, esperado) => expect(tempoDesde(iso, AGORA)).toBe(esperado));
  it("a missing or invalid value renders a dash, never 0", () => {
    expect(tempoDesde(null, AGORA)).toBe("—");
    expect(tempoDesde("lixo", AGORA)).toBe("—");
  });
});
