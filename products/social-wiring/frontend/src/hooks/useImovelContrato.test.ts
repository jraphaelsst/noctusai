/**
 * useImovelContrato — the wire contract for the contract-facing reads.
 *
 * Mocks `@tanstack/react-query` entirely (the `useMatriculaEstrutura.test.ts`
 * pattern): `mutate` / `_queryFn` are called directly, no QueryClientProvider.
 *
 * What matters here is the stuff a component test cannot see: WHICH envelope
 * each route answers with (`/api/matriculas/...` wraps in `data`,
 * `/api/imoveis/...` does not), that `null` really travels as `null`, and the
 * 30-day arithmetic at its boundary.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPut, mockPatch, invalidateQueriesMock, setQueryDataMock, toastError } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPut: vi.fn(),
    mockPatch: vi.fn(),
    invalidateQueriesMock: vi.fn(),
    setQueryDataMock: vi.fn(),
    toastError: vi.fn(),
  }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, put: mockPut, patch: mockPatch },
  useAuthStore: () => ({ user: { id: "u1" } }),
}));

vi.mock("sonner", () => ({ toast: { error: toastError, success: vi.fn() } }));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    _queryFn: queryFn,
    _enabled: enabled,
  }));
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
      onError,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
      onError?: (e: unknown) => void;
    }) => ({
      mutate: (vars: unknown) => {
        Promise.resolve(mutationFn(vars))
          .then((result) => onSuccess?.(result, vars))
          .catch((err) => onError?.(err));
      },
      isPending: false,
    }),
  );
  const useQueryClient = vi.fn(() => ({
    invalidateQueries: invalidateQueriesMock,
    setQueryData: setQueryDataMock,
  }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  CERTIDAO_MAX_DIAS,
  certidaoDesatualizada,
  diasDesdeEmissao,
  motivoSemSugestaoTexto,
  useAntigosProprietarios,
  useConfirmarDocumentoExtracao,
  useConfirmarOnusCredor,
  useConfirmarTitulo,
  useImovelCertidoes,
  useOnusCredor,
  useTituloAquisitivo,
} from "./useImovelContrato";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("reads", () => {
  it("GETs the título aquisitivo and stays disabled without a código", async () => {
    mockGet.mockResolvedValue({ data: { sugestao: null } });
    expect((useTituloAquisitivo(null) as any)._enabled).toBe(false);

    const hook = useTituloAquisitivo("AP1234") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/imoveis/AP1234/titulo-aquisitivo");
  });

  it("GETs the ônus creditor", async () => {
    mockGet.mockResolvedValue({ data: { atos: [] } });
    await (useOnusCredor("AP1234") as any)._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/imoveis/AP1234/onus-credor");
  });

  it("GETs the previous owners", async () => {
    mockGet.mockResolvedValue({ data: { transmitentes: [] } });
    await (useAntigosProprietarios("AP1234") as any)._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/matriculas/imoveis/AP1234/antigos-proprietarios",
    );
  });

  it("🔴 unwraps the imóvel routes' `{items}` envelope, not a `data` one", async () => {
    // The two modules answer with DIFFERENT envelopes; reading the wrong one
    // yields `undefined` and an empty card that looks like "no certidões".
    mockGet.mockResolvedValue({ items: [{ tipo: "cnd_iptu" }], total: 1 });
    const items = await (useImovelCertidoes("AP1234") as any)._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/imoveis/AP1234/certidoes");
    expect(items).toEqual([{ tipo: "cnd_iptu" }]);
  });

  it("encodes a código with characters that would break the path", async () => {
    mockGet.mockResolvedValue({ data: {} });
    await (useTituloAquisitivo("AP 1/2") as any)._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/matriculas/imoveis/AP%201%2F2/titulo-aquisitivo",
    );
  });
});

describe("useConfirmarTitulo", () => {
  it("PUTs the confirmed phrase and seeds the cache from the response", async () => {
    mockPut.mockResolvedValue({ data: { confirmado: { texto: "frase" } } });
    (useConfirmarTitulo("AP1234") as any).mutate("frase");
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith(
      "/api/matriculas/imoveis/AP1234/titulo-aquisitivo",
      { texto: "frase" },
    );
    await vi.waitFor(() => expect(setQueryDataMock).toHaveBeenCalled());
  });

  it("🔴 clearing sends an explicit null", async () => {
    mockPut.mockResolvedValue({ data: {} });
    (useConfirmarTitulo("AP1234") as any).mutate(null);
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith(
      "/api/matriculas/imoveis/AP1234/titulo-aquisitivo",
      { texto: null },
    );
  });

  it("surfaces the server's sentence without the status prefix", async () => {
    mockPut.mockRejectedValue(new Error("[400] O código do imóvel é obrigatório."));
    (useConfirmarTitulo("AP1234") as any).mutate("x");
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Não foi possível salvar o título aquisitivo", {
      description: "O código do imóvel é obrigatório.",
    });
  });
});

describe("useConfirmarOnusCredor", () => {
  it("PUTs the creditor", async () => {
    mockPut.mockResolvedValue({ data: {} });
    (useConfirmarOnusCredor("AP1234") as any).mutate("Banco X");
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/imoveis/AP1234/onus-credor", {
      credor: "Banco X",
    });
  });

  it("clearing sends an explicit null", async () => {
    mockPut.mockResolvedValue({ data: {} });
    (useConfirmarOnusCredor("AP1234") as any).mutate(null);
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/imoveis/AP1234/onus-credor", {
      credor: null,
    });
  });
});

describe("useConfirmarDocumentoExtracao", () => {
  it("🔴 PATCHes an EMPTY body to confirm a read as-is", async () => {
    // `{}` is a valid confirmation, not a no-op: it stamps `origem='manual'`
    // and LOCKS the row against a later retry overwriting it.
    mockPatch.mockResolvedValue({});
    (useConfirmarDocumentoExtracao("AP1234") as any).mutate({
      documentoId: "doc-1",
      patch: {},
    });
    await vi.waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/imoveis/AP1234/documentos/doc-1/extracao",
      {},
    );
  });

  it("PATCHes a correction and invalidates the certidões + dados caches", async () => {
    mockPatch.mockResolvedValue({});
    (useConfirmarDocumentoExtracao("AP1234") as any).mutate({
      documentoId: "doc-1",
      patch: { numero: "999", validade_ate: null },
    });
    await vi.waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch).toHaveBeenCalledWith("/api/imoveis/AP1234/documentos/doc-1/extracao", {
      numero: "999",
      validade_ate: null,
    });
    await vi.waitFor(() =>
      expect(invalidateQueriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sw", "imovel-dados", "AP1234"] }),
      ),
    );
  });

  it("surfaces the 400 naming a field the tipo does not carry", async () => {
    mockPatch.mockRejectedValue(
      new Error("[400] Campos não aplicáveis a guia_iptu: resultado"),
    );
    (useConfirmarDocumentoExtracao("AP1234") as any).mutate({
      documentoId: "doc-1",
      patch: { resultado: "negativa" },
    });
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Não foi possível confirmar a certidão", {
      description: "Campos não aplicáveis a guia_iptu: resultado",
    });
  });
});

describe("the 30-day office rule", () => {
  const hoje = new Date("2026-03-31T12:00:00Z");

  it("counts whole days from the printed emission date", () => {
    expect(diasDesdeEmissao("2026-03-31", hoje)).toBe(0);
    expect(diasDesdeEmissao("2026-03-02", hoje)).toBe(29);
    expect(diasDesdeEmissao("2026-03-01", hoje)).toBe(30);
  });

  it("🔴 gives the same answer at any hour of the same local day", () => {
    // The count is over CALENDAR days, so the 30-day verdict must not flip
    // mid-afternoon. Local constructor on purpose: "today" is whichever local
    // day the instant falls in, which is what the office counts.
    const manha = new Date(2026, 2, 31, 0, 30);
    const noite = new Date(2026, 2, 31, 23, 30);
    expect(diasDesdeEmissao("2026-03-01", manha)).toBe(
      diasDesdeEmissao("2026-03-01", noite),
    );
  });

  it("🔴 does not let a date-only `emitida_em` drift by a time zone", () => {
    // Read as LOCAL time, "2026-03-31" lands on the 30th west of Greenwich —
    // a one-day error exactly on the boundary. A certidão emitted today is 0
    // days old at both ends of today.
    expect(diasDesdeEmissao("2026-03-31", new Date(2026, 2, 31, 0, 30))).toBe(0);
    expect(diasDesdeEmissao("2026-03-31", new Date(2026, 2, 31, 23, 30))).toBe(0);
  });

  it("is honest about an absent or unparseable date", () => {
    expect(diasDesdeEmissao(null, hoje)).toBeNull();
    expect(diasDesdeEmissao("", hoje)).toBeNull();
    expect(diasDesdeEmissao("sem data", hoje)).toBeNull();
  });

  it("🔴 treats exactly 30 days as already too old ('less than 30' at signing)", () => {
    expect(CERTIDAO_MAX_DIAS).toBe(30);
    expect(certidaoDesatualizada("2026-03-02", hoje)).toBe(false);
    expect(certidaoDesatualizada("2026-03-01", hoje)).toBe(true);
  });

  it("never warns on a date it could not read — that is a different notice", () => {
    expect(certidaoDesatualizada(null, hoje)).toBe(false);
  });
});

describe("motivoSemSugestaoTexto", () => {
  it("explains each known reason in pt-BR", () => {
    expect(motivoSemSugestaoTexto("sem_instrumento")).toContain("instrumento");
    expect(motivoSemSugestaoTexto("sem_titulo_confirmado")).toContain("título aquisitivo");
    expect(motivoSemSugestaoTexto("sem_credor")).toContain("credor");
  });

  it("falls back to a readable sentence for a reason it does not know", () => {
    // A future backend reason must not render as a blank warning box.
    expect(motivoSemSugestaoTexto("motivo_novo")).toContain("confirme o valor manualmente");
  });

  it("returns null when there is no reason at all", () => {
    expect(motivoSemSugestaoTexto(null)).toBeNull();
  });
});
