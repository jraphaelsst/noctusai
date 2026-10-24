/**
 * F87 — after "Solicitar emissão" the first re-reads may show no cell in
 * flight yet; the poll must survive that, then stop once the cells settled.
 */
import { describe, expect, it } from "vitest";

import {
  EMISSAO_GRACE_MS,
  emissaoAguardandoAssentar,
  marcarEmissaoSolicitada,
} from "./useCertidoesPartes";
import type { CertidoesPartesResponse } from "@/types/certidoesPartes";

const resp = (status: string) =>
  ({
    partes: [{ celulas: { a: { status_processamento: status, aguarda_humano: false } } }],
  }) as unknown as CertidoesPartesResponse;

describe("emissaoAguardandoAssentar", () => {
  it("without a request, follows the data only", () => {
    expect(emissaoAguardandoAssentar("c0", resp("sucesso"))).toBe(false);
    expect(emissaoAguardandoAssentar("c0", resp("processando"))).toBe(true);
  });

  it("keeps polling while nothing is in flight yet, stops once seen-in-flight then settled", () => {
    const t = 1_000;
    marcarEmissaoSolicitada("c1", t);
    expect(emissaoAguardandoAssentar("c1", resp("sucesso"), t + 1000)).toBe(true);
    expect(emissaoAguardandoAssentar("c1", resp("processando"), t + 5000)).toBe(true);
    expect(emissaoAguardandoAssentar("c1", resp("sucesso"), t + 20000)).toBe(false);
    expect(emissaoAguardandoAssentar("c1", resp("sucesso"), t + 21000)).toBe(false);
  });

  it("gives up at the deadline when nothing ever started", () => {
    const t = 1_000;
    marcarEmissaoSolicitada("c2", t);
    expect(emissaoAguardandoAssentar("c2", resp("sucesso"), t + EMISSAO_GRACE_MS - 1)).toBe(true);
    expect(emissaoAguardandoAssentar("c2", resp("sucesso"), t + EMISSAO_GRACE_MS)).toBe(false);
  });
});
