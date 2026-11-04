/** Pure helpers: filters <-> URL, Instagram embed builder, handle normalization. */
import { describe, expect, it } from "vitest";

import {
  contarFiltrosAtivos,
  embedUrlInstagram,
  FILTROS_VAZIOS,
  filtrosDeParams,
  filtrosParaParams,
} from "./filtros";
import { normalizarHandle } from "./handle";

describe("filtros <-> URL", () => {
  it("defaults round-trip to an empty query string", () => {
    expect(filtrosParaParams(FILTROS_VAZIOS).toString()).toBe("");
    expect(filtrosDeParams(new URLSearchParams(""))).toEqual(FILTROS_VAZIOS);
  });

  it("round-trips every active filter", () => {
    const f = {
      ...FILTROS_VAZIOS,
      nichos: [3, 5],
      profissoes: [9],
      verTodos: true,
      ordem: "mais_recentes" as const,
      q: "obra, reforma",
      buscarEm: "transcricao" as const,
      dataDe: "2026-01-01",
      viewsMin: 100000,
      likesMin: 10000,
      perfilId: "p1",
      formatoId: 4,
      codigo: 77,
      somenteVirais: false,
      page: 3,
    };
    expect(filtrosDeParams(filtrosParaParams(f))).toEqual(f);
    expect(contarFiltrosAtivos(f)).toBeGreaterThan(5);
  });

  it("ignores garbage numbers", () => {
    const f = filtrosDeParams(new URLSearchParams("nichos=abc&views_min=-3&page=x"));
    expect(f.nichos).toEqual([]);
    expect(f.viewsMin).toBeNull();
    expect(f.page).toBe(1);
  });
});

describe("embedUrlInstagram", () => {
  it("builds the embed for p/reel/tv permalinks", () => {
    expect(embedUrlInstagram("https://www.instagram.com/reel/Abc_12-x/")).toBe(
      "https://www.instagram.com/p/Abc_12-x/embed/",
    );
    expect(embedUrlInstagram("https://instagram.com/p/XyZ/?igsh=1")).toBe(
      "https://www.instagram.com/p/XyZ/embed/",
    );
    expect(embedUrlInstagram("https://www.instagram.com/tv/Q1/")).toContain("/p/Q1/embed/");
  });

  it.each([
    "http://www.instagram.com/p/abc/",
    "https://evil.com/p/abc/",
    "https://instagram.com.evil.com/p/abc/",
    "https://www.instagram.com/stories/user/123/",
    "javascript:alert(1)",
    "not a url",
    "",
    null,
  ])("rejects %s", (u) => {
    expect(embedUrlInstagram(u as string | null)).toBeNull();
  });
});

describe("normalizarHandle", () => {
  it("accepts @handle, bare handle and profile URLs", () => {
    expect(normalizarHandle(" @Fulano.Silva ")).toEqual({ ok: true, handle: "fulano.silva" });
    expect(normalizarHandle("fulano_1")).toEqual({ ok: true, handle: "fulano_1" });
    expect(normalizarHandle("https://www.instagram.com/fulano/?hl=pt")).toEqual({
      ok: true,
      handle: "fulano",
    });
  });

  it("rejects reserved segments, empty and invalid", () => {
    expect(normalizarHandle("https://instagram.com/reel/abc/").ok).toBe(false);
    expect(normalizarHandle("@explore").ok).toBe(false);
    expect(normalizarHandle("").ok).toBe(false);
    expect(normalizarHandle("@com espaço").ok).toBe(false);
    expect(normalizarHandle("@" + "a".repeat(31)).ok).toBe(false);
  });
});
