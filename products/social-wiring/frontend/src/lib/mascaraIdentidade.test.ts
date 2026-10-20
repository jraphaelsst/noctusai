import { describe, it, expect } from "vitest";

import { desescaparEntidades, mascararIdentidade } from "./mascaraIdentidade";

describe("mascararIdentidade", () => {
  it("masks a dotted CPF down to its last two digits", () => {
    expect(mascararIdentidade("CPF 123.456.789-09 do lead")).not.toContain("123.456");
    expect(mascararIdentidade("123.456.789-09")).toBe("***.***.***-09");
  });
  it("masks an undotted CPF", () => {
    expect(mascararIdentidade("12345678909")).toBe("***.***.***-09");
  });
  it("masks the value after an rg/cpf label", () => {
    const out = mascararIdentidade("rg: 12.345.678-9; cpf: 123.456.789-09");
    expect(out).not.toMatch(/12\.345|123\.456/);
    expect(out).toMatch(/rg: \*+89/);
  });
  it("leaves already-masked values and ordinary numbers alone (idempotent)", () => {
    const m = "cpf: ***.***.***-09; rg: ******78; 3 quartos, R$ 450.000";
    expect(mascararIdentidade(m)).toBe(m);
    expect(mascararIdentidade(mascararIdentidade("123.456.789-09"))).toBe("***.***.***-09");
  });
  it("undoes server-side html entities for display", () => {
    expect(desescaparEntidades("Ana &amp; Beto &lt;3 &#x27;oi&#x27;")).toBe("Ana & Beto <3 'oi'");
  });
});
