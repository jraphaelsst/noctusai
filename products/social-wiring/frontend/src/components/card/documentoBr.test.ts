/**
 * `documentoBr` is a thin adapter over the ONE identifier seam
 * (`@noctusai/lib/identificador`, owner rule 2026-10-01 — it used to carry its
 * own copy of the CPF / CNPJ mod-11 code). What is pinned here: the lookup
 * gate behaves exactly as before for CPF / CNPJ, and a stored document renders
 * in its canonical PUNCTUATED form.
 */
import { describe, expect, it } from "vitest";

import {
  cnpjValido,
  cpfValido,
  documentoParaLookup,
  formatarDocumentoArmazenado,
} from "./documentoBr";

describe("cpfValido / cnpjValido (check digits via the seam)", () => {
  it("accepts a CPF in any spelling and rejects a wrong check digit or a repdigit", () => {
    expect(cpfValido("412.954.238-98")).toBe(true);
    expect(cpfValido("41295423898")).toBe(true);
    expect(cpfValido("412.954.238-99")).toBe(false);
    expect(cpfValido("111.111.111-11")).toBe(false);
    expect(cpfValido("4129542389")).toBe(false);
  });

  it("accepts a CNPJ (numeric or alphanumeric) and rejects a wrong check digit", () => {
    expect(cnpjValido("11.222.333/0001-81")).toBe(true);
    expect(cnpjValido("11222333000181")).toBe(true);
    expect(cnpjValido("12.ABC.345/01DE-35")).toBe(true);
    expect(cnpjValido("11.222.333/0001-82")).toBe(false);
  });
});

describe("documentoParaLookup", () => {
  it("returns the key to look up only once the document fits the chosen kind of person", () => {
    expect(documentoParaLookup("412.954.238-98", "PF")).toBe("41295423898");
    expect(documentoParaLookup("41295423", "PF")).toBeNull(); // half-typed: no round trip
    expect(documentoParaLookup("11.222.333/0001-81", "PJ")).toBe("11222333000181");
    expect(documentoParaLookup("412.954.238-98", "PJ")).toBeNull(); // a CPF is not a CNPJ
    expect(documentoParaLookup("11.222.333/0001-82", "PJ")).toBeNull();
  });

  it("keeps an alphanumeric CNPJ intact (never strips its letters)", () => {
    expect(documentoParaLookup("12.ABC.345/01DE-35", "PJ")).toBe("12ABC34501DE35");
  });
});

describe("formatarDocumentoArmazenado", () => {
  it("renders a stored CPF / CNPJ in its canonical punctuated form, whatever it was stored as", () => {
    expect(formatarDocumentoArmazenado("41295423898")).toBe("412.954.238-98");
    expect(formatarDocumentoArmazenado("412.954.238-98")).toBe("412.954.238-98");
    expect(formatarDocumentoArmazenado("11222333000181")).toBe("11.222.333/0001-81");
  });

  it("shows a value that does not fit its type exactly as stored — visible, never hidden", () => {
    expect(formatarDocumentoArmazenado("41295423899")).toBe("41295423899"); // bad DV
    expect(formatarDocumentoArmazenado("abc")).toBe("abc");
    expect(formatarDocumentoArmazenado(null)).toBe("");
  });
});
