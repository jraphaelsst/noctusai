/**
 * certidoesEstruturadas.test.ts — the pure value helpers contract
 * automation F1 + F6 render off (`CertidoesPartePanel`).
 *
 * What these protect:
 *   1. `situacaoCadastralBadge`'s office-rule verdict, including the exact
 *      5-year `baixada` boundary (`ha_menos_de_anos`'s own contract: "exactly
 *      N years earlier is not less than" — mirrored from the backend's
 *      `contrato_gerador/derivacao.py`).
 *   2. `isEmissaoAntiga`'s ≥30-day signing-window flag.
 *   3. `negativa_com_homonimos` is a real, labelled `ResultadoValor`.
 *
 * Dates are computed relative to the REAL "today" at test-run time (never
 * hardcoded), the same reasoning `isValidadeVencida`'s own no-timezone-shift
 * parsing exists for — a hardcoded date would eventually land on the wrong
 * side of "today" and the test would silently stop testing the boundary.
 */
import { describe, it, expect } from "vitest";
import {
  RESULTADO_VALOR_LABELS,
  isEmissaoAntiga,
  situacaoCadastralBadge,
  type ResultadoValor,
} from "./certidoesEstruturadas";

/** Local-date (no UTC shift) `YYYY-MM-DD`, matching how every date field in
 *  this module is parsed (`new Date(y, m - 1, d)`, never `Date.parse`). */
function isoLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** `anos` years before today, shifted by `ajusteDias` days (positive = more
 *  recent, negative = older) — the exact-boundary knob the 5-year tests need. */
function dataAnosAtras(anos: number, ajusteDias: number = 0): string {
  const hoje = new Date();
  const alvo = new Date(hoje.getFullYear() - anos, hoje.getMonth(), hoje.getDate());
  alvo.setDate(alvo.getDate() + ajusteDias);
  return isoLocal(alvo);
}

function diasAtras(dias: number): string {
  const hoje = new Date();
  const alvo = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - dias);
  return isoLocal(alvo);
}

describe("situacaoCadastralBadge", () => {
  it("ativa is always exigida no contrato", () => {
    expect(situacaoCadastralBadge("ativa", null).kind).toBe("exigida");
  });

  it("inapta is always exigida no contrato", () => {
    expect(situacaoCadastralBadge("inapta", null).kind).toBe("exigida");
  });

  it("suspensa is always fora do contrato", () => {
    expect(situacaoCadastralBadge("suspensa", dataAnosAtras(0, 1)).kind).toBe("fora");
  });

  it("nula is always fora do contrato", () => {
    expect(situacaoCadastralBadge("nula", dataAnosAtras(0, 1)).kind).toBe("fora");
  });

  it("no situacao_cadastral at all is situação desconhecida", () => {
    expect(situacaoCadastralBadge(null, null).kind).toBe("desconhecida");
  });

  it("baixada with no data_situacao is situação desconhecida (age genuinely unknown)", () => {
    expect(situacaoCadastralBadge("baixada", null).kind).toBe("desconhecida");
  });

  it("baixada less than 5 years ago (one day inside the window) is exigida", () => {
    const badge = situacaoCadastralBadge("baixada", dataAnosAtras(5, 1));
    expect(badge.kind).toBe("exigida");
  });

  it("🔴 baixada exactly 5 years ago is fora — the boundary itself is NOT 'less than'", () => {
    const badge = situacaoCadastralBadge("baixada", dataAnosAtras(5, 0));
    expect(badge.kind).toBe("fora");
  });

  it("baixada more than 5 years ago (one day past the boundary) is fora", () => {
    const badge = situacaoCadastralBadge("baixada", dataAnosAtras(5, -1));
    expect(badge.kind).toBe("fora");
  });

  it("baixada well within 5 years (1 year ago) is exigida", () => {
    expect(situacaoCadastralBadge("baixada", dataAnosAtras(1, 0)).kind).toBe("exigida");
  });

  it("baixada well past 5 years (10 years ago) is fora", () => {
    expect(situacaoCadastralBadge("baixada", dataAnosAtras(10, 0)).kind).toBe("fora");
  });
});

describe("isEmissaoAntiga", () => {
  it("returns false for a null/undefined emitida_em", () => {
    expect(isEmissaoAntiga(null)).toBe(false);
    expect(isEmissaoAntiga(undefined)).toBe(false);
  });

  it("returns false for an emission younger than 30 days", () => {
    expect(isEmissaoAntiga(diasAtras(29))).toBe(false);
  });

  it("🔴 returns true at exactly 30 days — the rule's own '≥ 30 days' wording", () => {
    expect(isEmissaoAntiga(diasAtras(30))).toBe(true);
  });

  it("returns true for an emission well past 30 days", () => {
    expect(isEmissaoAntiga(diasAtras(45))).toBe(true);
  });

  it("honours a custom threshold", () => {
    expect(isEmissaoAntiga(diasAtras(10), 5)).toBe(true);
    expect(isEmissaoAntiga(diasAtras(3), 5)).toBe(false);
  });
});

describe("negativa_com_homonimos (migration 116)", () => {
  it("is a real, labelled resultado value — never falls back to the raw key", () => {
    const valor: ResultadoValor = "negativa_com_homonimos";
    expect(RESULTADO_VALOR_LABELS[valor]).toBe("Negativa c/ homônimos");
  });
});
