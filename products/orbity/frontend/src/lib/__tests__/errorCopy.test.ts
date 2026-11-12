import { describe, expect, it } from "vitest";

import { ERROR_COPY, errorCopy } from "@/lib/errorCopy";

const apiError = (status: number, detail: unknown) =>
  Object.assign(new Error(`[${status}] ${String(detail)}`), { body: { error: { code: "HTTP_ERROR", message: detail } } });
const flatError = (status: number, detail: string) =>
  Object.assign(new Error(`[${status}] ${detail}`), { body: { detail, code: "cliente_com_pendencias" } });

describe("errorCopy", () => {
  it("turns a known server code into its pt-BR copy, never the raw code", () => {
    const text = errorCopy(apiError(404, "lead_not_found"));
    expect(text).toBe(ERROR_COPY.lead_not_found);
    expect(text).not.toContain("lead_not_found");
  });

  it("keeps the server's own curated text for a detail it has no code for (never silent)", () => {
    expect(errorCopy(apiError(400, "Nenhum campo para atualizar"))).toBe("Nenhum campo para atualizar");
  });

  it("reads the seed's flat {detail} refusals too", () => {
    expect(errorCopy(flatError(409, "O cliente tem 1 contrato ativo"))).toBe("O cliente tem 1 contrato ativo");
  });

  it("is undefined for a non-error", () => {
    expect(errorCopy(null)).toBeUndefined();
  });

  it("has copy for every code the backend raises", () => {
    for (const code of ["post_not_promotable", "invalid_stage", "invalid_month", "report_not_found", "cobrancas_em_aberto"]) {
      expect(ERROR_COPY[code]).toBeTruthy();
    }
  });
});
