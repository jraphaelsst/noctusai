/**
 * useProveniencia — `sw-extraction-contract`'s FROZEN
 * `GET /clientes/{cliente_id}/contratos/{contrato_id}/proveniencia`.
 *
 * Mocks `@tanstack/react-query` (same pattern `useContratos.test.ts` uses)
 * so the query FUNCTION + `enabled` gate are exercised directly with no
 * `QueryClientProvider` needed. Coverage: the URL shape, the lazy `aberto`
 * gate, `rotuloDaEntrada`'s pt-BR mapping (+ raw-value fallback), and
 * `destinoDoDocumento`'s FE-side entrada→place heuristic.
 */
import { describe, expect, it, vi } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
    _queryFn: queryFn,
    _enabled: enabled,
  }));
  return { useQuery };
});

import { destinoDoDocumento, rotuloDaEntrada, useProveniencia } from "./useProveniencia";

describe("useProveniencia", () => {
  it("is gated by `aberto` AND both ids — the lazy-fetch discipline `useContratoGeracao` also uses", async () => {
    const { useQuery } = await import("@tanstack/react-query");

    useProveniencia("cli1", "c1", false);
    expect(vi.mocked(useQuery).mock.calls[0][0]).toMatchObject({ enabled: false });

    useProveniencia(null, "c1", true);
    expect(vi.mocked(useQuery).mock.calls[1][0]).toMatchObject({ enabled: false });

    useProveniencia("cli1", null, true);
    expect(vi.mocked(useQuery).mock.calls[2][0]).toMatchObject({ enabled: false });

    useProveniencia("cli1", "c1", true);
    expect(vi.mocked(useQuery).mock.calls[3][0]).toMatchObject({ enabled: true });
  });

  it("fetches the FROZEN route, ids URI-encoded", async () => {
    mockGet.mockResolvedValueOnce({ items: [] });
    const { useQuery } = await import("@tanstack/react-query");
    useProveniencia("cli 1", "c/1", true);
    const calls = vi.mocked(useQuery).mock.calls;
    const call = calls[calls.length - 1][0] as unknown as { queryFn: () => unknown };
    await call.queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/clientes/cli%201/contratos/c%2F1/proveniencia",
    );
  });
});

describe("rotuloDaEntrada", () => {
  it("maps every contract entrada value to a pt-BR label", () => {
    expect(rotuloDaEntrada("lead_form")).toBe("Formulário de lead");
    expect(rotuloDaEntrada("cliente_card_upload")).toBe("Upload no card do cliente");
    expect(rotuloDaEntrada("parte_painel_upload")).toBe("Upload no painel da parte");
    expect(rotuloDaEntrada("imovel_page_upload")).toBe("Upload na página do imóvel");
    expect(rotuloDaEntrada("matriculas")).toBe("Extrator de matrículas");
    expect(rotuloDaEntrada("vista_mirror")).toBe("Espelho do Vista");
    expect(rotuloDaEntrada("certidao_robo")).toBe("Robô de certidões");
    expect(rotuloDaEntrada("manual")).toBe("Digitado manualmente");
    expect(rotuloDaEntrada("derivado")).toBe("Calculado a partir de outros dados");
  });

  it("falls back to the raw value for an unknown entrada, never a blank string", () => {
    expect(rotuloDaEntrada("algo_novo")).toBe("algo_novo");
  });

  it("renders '—' for null/undefined", () => {
    expect(rotuloDaEntrada(null)).toBe("—");
    expect(rotuloDaEntrada(undefined)).toBe("—");
  });
});

describe("destinoDoDocumento", () => {
  it("resolves a document-bearing entrada to a route or a card subpage key", () => {
    expect(destinoDoDocumento("lead_form")).toBe("/leads");
    expect(destinoDoDocumento("imovel_page_upload")).toBe("/imoveis");
    expect(destinoDoDocumento("matriculas")).toBe("/matriculas");
    expect(destinoDoDocumento("certidao_robo")).toBe("/certidoes");
    expect(destinoDoDocumento("cliente_card_upload")).toBe("geral");
    expect(destinoDoDocumento("parte_painel_upload")).toBe("geral");
  });

  it("has no place to send the operator for vista_mirror/manual/derivado", () => {
    expect(destinoDoDocumento("vista_mirror")).toBeNull();
    expect(destinoDoDocumento("manual")).toBeNull();
    expect(destinoDoDocumento("derivado")).toBeNull();
  });

  it("is null for null/undefined", () => {
    expect(destinoDoDocumento(null)).toBeNull();
    expect(destinoDoDocumento(undefined)).toBeNull();
  });
});
