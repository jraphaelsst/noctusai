/**
 * useMatriculaEstrutura — atos / fontes / contract-selection hooks.
 *
 * Mocks `@tanstack/react-query` entirely (`useN8nWorkflows.test.ts`'s
 * pattern) — `mutate`/`_queryFn` are called directly, no QueryClientProvider.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPut, invalidateQueriesMock, setQueryDataMock, toastError } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
  invalidateQueriesMock: vi.fn(),
  setQueryDataMock: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, put: mockPut },
}));

vi.mock("sonner", () => ({
  toast: { error: toastError, success: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
    data: undefined,
    isPending: false,
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
  useConfirmarDetalhesAto,
  useContratoAtos,
  useDefinirContratoAtos,
  useDefinirFontes,
  useMatriculaAtos,
  useMatriculaFontes,
} from "./useMatriculaEstrutura";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useMatriculaAtos", () => {
  it("GETs the extraction's acts and stays disabled without an id", async () => {
    mockGet.mockResolvedValue({ data: { atos: [] } });
    const disabled = useMatriculaAtos(null) as any;
    expect(disabled._enabled).toBe(false);

    const hook = useMatriculaAtos("extracao-1") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/extracoes/extracao-1/atos");
  });
});

describe("useMatriculaFontes", () => {
  it("GETs the extraction's fontes", async () => {
    mockGet.mockResolvedValue({ data: { titulo_aquisitivo: null, onus: null } });
    const hook = useMatriculaFontes("extracao-1") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/extracoes/extracao-1/fontes");
  });
});

describe("useDefinirFontes", () => {
  it("🔴 confirming a título aquisitivo PUTs the ato_id and invalidates the imóvel cartório card's cache", async () => {
    mockPut.mockResolvedValue({ data: { titulo_aquisitivo: { ato_id: "ato-1" } } });
    const hook = useDefinirFontes("extracao-1") as any;
    hook.mutate({ titulo_aquisitivo_ato_id: "ato-1" });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/extracoes/extracao-1/fontes", {
      titulo_aquisitivo_ato_id: "ato-1",
    });
    await vi.waitFor(() =>
      expect(invalidateQueriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sw", "imovel-dados"] }),
      ),
    );
  });

  it("clearing sends null, not an omitted key", async () => {
    mockPut.mockResolvedValue({ data: {} });
    const hook = useDefinirFontes("extracao-1") as any;
    hook.mutate({ titulo_aquisitivo_ato_id: null });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/extracoes/extracao-1/fontes", {
      titulo_aquisitivo_ato_id: null,
    });
  });

  it("surfaces the server's error on a 400 (not concluída / no imóvel link)", async () => {
    mockPut.mockRejectedValue(new Error("[400] A transcrição ainda não foi concluída."));
    const hook = useDefinirFontes("extracao-1") as any;
    hook.mutate({ onus_ato_ids: ["ato-2"] });
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Não foi possível salvar a fonte", {
      description: "A transcrição ainda não foi concluída.",
    });
  });
});

describe("useContratoAtos", () => {
  it("GETs the contract's selected acts", async () => {
    mockGet.mockResolvedValue({ data: { atos: [], texto: "" } });
    const hook = useContratoAtos("contrato-1") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/contratos/contrato-1/atos");
  });
});

describe("useDefinirContratoAtos", () => {
  it("PUTs extracao_id + ato_ids in contract order", async () => {
    mockPut.mockResolvedValue({ data: { atos: [] } });
    const hook = useDefinirContratoAtos("contrato-1") as any;
    hook.mutate({ extracaoId: "extracao-1", atoIds: ["ato-2", "ato-1"] });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/contratos/contrato-1/atos", {
      extracao_id: "extracao-1",
      ato_ids: ["ato-2", "ato-1"],
      // Always sent, even empty: the PUT REPLACES the whole selection, so an
      // omitted `permutas` would be indistinguishable from "delete them".
      permutas: [],
    });
  });

  it("🔴 clearing (empty ato_ids) omits extracao_id — an empty selection needs no matrícula", async () => {
    mockPut.mockResolvedValue({ data: { atos: [] } });
    const hook = useDefinirContratoAtos("contrato-1") as any;
    hook.mutate({ extracaoId: "extracao-1", atoIds: [] });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/contratos/contrato-1/atos", {
      extracao_id: undefined,
      ato_ids: [],
      permutas: [],
    });
  });

  it("🔴 sends every permuta group in the SAME body as the object's quote", async () => {
    // One PUT replaces the object's acts AND every permuta's, so a group left
    // out of this body is a group deleted — which is why the container holds
    // all the drafts and composes them here.
    mockPut.mockResolvedValue({ data: { atos: [], permutas: [] } });
    const hook = useDefinirContratoAtos("contrato-1") as any;
    hook.mutate({
      extracaoId: "extracao-1",
      atoIds: ["ato-1"],
      permutas: [
        { permutaAtivoId: "ativo-1", extracaoId: "extracao-7", atoIds: ["ato-9", "ato-8"] },
      ],
    });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/contratos/contrato-1/atos", {
      extracao_id: "extracao-1",
      ato_ids: ["ato-1"],
      permutas: [
        { permuta_ativo_id: "ativo-1", extracao_id: "extracao-7", ato_ids: ["ato-9", "ato-8"] },
      ],
    });
  });
});

describe("useConfirmarDetalhesAto", () => {
  it("🔴 PUTs an EMPTY body to confirm the suggestion as it stands", async () => {
    // `{}` means "I reviewed this and it is correct". Sending the current
    // values instead would re-stamp every field as human-typed and erase the
    // extractor's own confidence.
    mockPut.mockResolvedValue({ data: { ato_id: "ato-1", detalhes: {} } });
    const hook = useConfirmarDetalhesAto("extracao-1") as any;
    hook.mutate({ atoId: "ato-1", patch: {} });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/atos/ato-1/detalhes", {});
  });

  it("🔴 passes a cleared field through as null, not as an omitted key", async () => {
    // Absent = keep the suggestion; null = clear it. Collapsing the two would
    // make "the extractor read something that is not there" unfixable.
    mockPut.mockResolvedValue({ data: { ato_id: "ato-1", detalhes: {} } });
    const hook = useConfirmarDetalhesAto("extracao-1") as any;
    hook.mutate({ atoId: "ato-1", patch: { valor: null, transmitentes: [] } });
    await vi.waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/atos/ato-1/detalhes", {
      valor: null,
      transmitentes: [],
    });
  });

  it("patches the one act in the cached list and invalidates the imóvel reads", async () => {
    mockPut.mockResolvedValue({
      data: { ato_id: "ato-1", detalhes: { origem: "confirmado" } },
    });
    const hook = useConfirmarDetalhesAto("extracao-1") as any;
    hook.mutate({ atoId: "ato-1", patch: {} });
    await vi.waitFor(() => expect(setQueryDataMock).toHaveBeenCalled());

    // The cache update is an updater FUNCTION (the response carries only the
    // act it wrote), so re-reading the whole list would collapse every open
    // editor on the page.
    const [chave, updater] = setQueryDataMock.mock.calls[0];
    expect(chave).toEqual(["matricula-atos", "extracao-1"]);
    const antes = {
      atos: [
        { id: "ato-1", detalhes: { origem: "sugestao" } },
        { id: "ato-2", detalhes: { origem: "sugestao" } },
      ],
    };
    expect((updater as (v: unknown) => any)(antes).atos).toEqual([
      { id: "ato-1", detalhes: { origem: "confirmado" } },
      { id: "ato-2", detalhes: { origem: "sugestao" } },
    ]);
    // The título/ônus/antigos reads are DERIVED from these details.
    await vi.waitFor(() =>
      expect(invalidateQueriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sw", "imovel-contrato"] }),
      ),
    );
  });

  it("leaves the cache alone when there is nothing cached yet", async () => {
    mockPut.mockResolvedValue({ data: { ato_id: "ato-1", detalhes: {} } });
    const hook = useConfirmarDetalhesAto("extracao-1") as any;
    hook.mutate({ atoId: "ato-1", patch: {} });
    await vi.waitFor(() => expect(setQueryDataMock).toHaveBeenCalled());
    const [, updater] = setQueryDataMock.mock.calls[0];
    expect((updater as (v: unknown) => unknown)(undefined)).toBeUndefined();
  });

  it("surfaces the server's refusal without the status prefix", async () => {
    mockPut.mockRejectedValue(
      new Error("[400] A abertura da matrícula não é um ato — não tem detalhes."),
    );
    const hook = useConfirmarDetalhesAto("extracao-1") as any;
    hook.mutate({ atoId: "ato-0", patch: {} });
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Não foi possível confirmar os detalhes", {
      description: "A abertura da matrícula não é um ato — não tem detalhes.",
    });
  });
});
