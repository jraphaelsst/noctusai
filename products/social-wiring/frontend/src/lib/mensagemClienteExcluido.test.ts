import { describe, expect, it } from "vitest";
import { mensagemClienteExcluido } from "./mensagemClienteExcluido";

const base = { deleted: true, atendimentos_removidos: 0, documentos_removidos: 0, storage_falhas: [] };

describe("mensagemClienteExcluido", () => {
  it("says the person won't come back from their leads when origens were blocked", () => {
    expect(mensagemClienteExcluido({ ...base, origens_bloqueadas: 3 })).toMatch(/não voltará.*3 lead\(s\)/);
  });
  it("stays plain when none / field absent", () => {
    expect(mensagemClienteExcluido(base)).toBe("Cliente excluído.");
    expect(mensagemClienteExcluido({ ...base, origens_bloqueadas: 0 })).toBe("Cliente excluído.");
  });
});
