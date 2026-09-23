/**
 * useContratos — the "Enviar para assinatura" additions
 * (signature-integration-CONTRACT §3/§4).
 *
 * Mocks `@tanstack/react-query` entirely (same pattern `useMatriculas.test.ts`/
 * `useN8nWorkflows.test.ts` use) so the query/mutation FUNCTIONS are exercised
 * directly, with no `QueryClientProvider` needed. Coverage:
 *   · `useAssinaturas` — one `useQueries` entry per contrato id, and the ONE
 *     translation the FE owns: 404 `ASSINATURA_NAO_ENCONTRADA` → `null`
 *     (never an error).
 *   · `enviarParaAssinatura`/`cancelarAssinatura` — the request body shape and
 *     the `ApiError` → `AssinaturaError` translation (`code`/`details`
 *     preserved, message prefers the server's own `error.message`).
 *   · `envelopeVivo` — `pendente`/`parcial` only, never bare truthiness.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const { mockGet, mockPost, invalidateQueriesMock, setQueryDataMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  invalidateQueriesMock: vi.fn(),
  setQueryDataMock: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
    data: undefined,
    isPending: false,
    isError: false,
    _queryFn: queryFn,
    _enabled: enabled,
  }));
  const useQueries = vi.fn(
    ({ queries }: { queries: Array<{ queryKey: unknown; queryFn: () => unknown; enabled?: boolean }> }) =>
      queries.map((q) => ({
        data: undefined,
        isPending: true,
        isFetching: false,
        isError: false,
        _queryFn: q.queryFn,
        _enabled: q.enabled,
      })),
  );
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
    }) => ({
      mutate: (
        vars: unknown,
        opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void },
      ) => {
        Promise.resolve(mutationFn(vars))
          .then((result) => {
            onSuccess?.(result, vars);
            opts?.onSuccess?.(result);
          })
          .catch((err) => {
            opts?.onError?.(err);
          });
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({
    invalidateQueries: invalidateQueriesMock,
    setQueryData: setQueryDataMock,
  }));
  return { useQuery, useQueries, useMutation, useQueryClient };
});

import {
  AssinaturaError,
  envelopeVivo,
  useAssinaturas,
  useContratoMutations,
  validateContratoAssinadoFile,
  versaoParaImpressao,
  type AssinaturaOut,
  type ContratoOut,
  type VersaoOut,
} from "./useContratos";

beforeEach(() => {
  vi.clearAllMocks();
});

function assinatura(over: Partial<AssinaturaOut> = {}): AssinaturaOut {
  return {
    assinatura_id: "as1",
    external_id: "ext1",
    link_assinatura: "https://d4sign.example/ext1",
    provedor: "d4sign",
    status: "pendente",
    signatarios: [],
    enviado_em: "2026-09-17T20:00:00Z",
    ...over,
  };
}

describe("envelopeVivo", () => {
  it("is true only for pendente/parcial", () => {
    expect(envelopeVivo(assinatura({ status: "pendente" }))).toBe(true);
    expect(envelopeVivo(assinatura({ status: "parcial" }))).toBe(true);
    expect(envelopeVivo(assinatura({ status: "concluido" }))).toBe(false);
    expect(envelopeVivo(assinatura({ status: "cancelado" }))).toBe(false);
    expect(envelopeVivo(assinatura({ status: "expirado" }))).toBe(false);
  });

  it("is false for null/undefined — never throws on 'no envelope yet'", () => {
    expect(envelopeVivo(null)).toBe(false);
    expect(envelopeVivo(undefined)).toBe(false);
  });
});

describe("useAssinaturas", () => {
  it("fires one GET per contrato id, scoped under the clienteId/contratoId key", async () => {
    mockGet.mockResolvedValueOnce(assinatura());
    const map = useAssinaturas("cli1", ["c1", "c2"]);
    expect(Object.keys(map)).toEqual(["c1", "c2"]);
    // The queryFn closures are captured by the `useQueries` mock's own call
    // args — invoke the first one to exercise the real fetch path.
    const { useQueries } = await import("@tanstack/react-query");
    const queries = (
      vi.mocked(useQueries).mock.calls[0][0] as unknown as { queries: Array<{ queryFn: () => unknown }> }
    ).queries;
    await queries[0].queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cli1/contratos/c1/assinatura");
  });

  it("🔴 translates a 404 ASSINATURA_NAO_ENCONTRADA into `null`, not an error", async () => {
    mockGet.mockRejectedValueOnce(
      new ApiError(404, "Não encontrado", { error: { code: "ASSINATURA_NAO_ENCONTRADA" } }),
    );
    useAssinaturas("cli1", ["c1"]);
    const queryFn = (
      vi.mocked((await import("@tanstack/react-query")).useQueries).mock.calls[0][0] as unknown as {
        queries: Array<{ queryFn: () => Promise<unknown> }>;
      }
    ).queries[0].queryFn;
    await expect(queryFn()).resolves.toBeNull();
  });

  it("re-throws a non-404 failure — a real query error, not 'no envelope'", async () => {
    mockGet.mockRejectedValueOnce(new ApiError(500, "Boom"));
    useAssinaturas("cli1", ["c1"]);
    const queryFn = (
      vi.mocked((await import("@tanstack/react-query")).useQueries).mock.calls[0][0] as unknown as {
        queries: Array<{ queryFn: () => Promise<unknown> }>;
      }
    ).queries[0].queryFn;
    await expect(queryFn()).rejects.toThrow("Boom");
  });
});

describe("useContratoMutations — enviarParaAssinatura / cancelarAssinatura", () => {
  it("§3.1 POSTs versao_id + signatarios (ordem defaults to 0) + trims mensagem", async () => {
    mockPost.mockResolvedValueOnce(assinatura());
    const { enviarParaAssinatura } = useContratoMutations("cli1");
    enviarParaAssinatura.mutate({
      contratoId: "c1",
      versaoId: "v1",
      signatarios: [
        { nome: "Ana", email: "ana@x.com", cpf: "12345678901", papel: "comprador" },
      ],
      mensagem: "  Olá  ",
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli1/contratos/c1/assinatura", {
      versao_id: "v1",
      signatarios: [
        { nome: "Ana", email: "ana@x.com", cpf: "12345678901", papel: "comprador", ordem: 0 },
      ],
      mensagem: "Olá",
    });
  });

  it("§3.1 omits mensagem entirely when blank", async () => {
    mockPost.mockResolvedValueOnce(assinatura());
    const { enviarParaAssinatura } = useContratoMutations("cli1");
    enviarParaAssinatura.mutate({
      contratoId: "c1",
      versaoId: "v1",
      signatarios: [{ nome: "Ana", email: "ana@x.com", cpf: "1", papel: "testemunha" }],
      mensagem: "   ",
    });
    await Promise.resolve();
    await Promise.resolve();
    const body = mockPost.mock.calls[0][1] as { mensagem?: string };
    expect(body.mensagem).toBeUndefined();
  });

  it("🔴 422 ASSINATURA_PROVEDOR_NAO_CONFIGURADO becomes an AssinaturaError carrying details.faltando", async () => {
    mockPost.mockRejectedValueOnce(
      new ApiError(422, "fallback", {
        error: {
          code: "ASSINATURA_PROVEDOR_NAO_CONFIGURADO",
          message: "Configure a plataforma de assinatura em Configurações.",
          details: { faltando: ["d4sign_api_token", "d4sign_safe_uuid"] },
        },
      }),
    );
    const { enviarParaAssinatura } = useContratoMutations("cli1");
    let captured: unknown;
    enviarParaAssinatura.mutate(
      {
        contratoId: "c1",
        versaoId: "v1",
        signatarios: [{ nome: "Ana", email: "a@x.com", cpf: "1", papel: "comprador" }],
      },
      { onError: (e) => (captured = e) },
    );
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(captured).toBeInstanceOf(AssinaturaError);
    const err = captured as AssinaturaError;
    expect(err.code).toBe("ASSINATURA_PROVEDOR_NAO_CONFIGURADO");
    expect(err.message).toBe("Configure a plataforma de assinatura em Configurações.");
    expect(err.details?.faltando).toEqual(["d4sign_api_token", "d4sign_safe_uuid"]);
  });

  it("🔴 409 ASSINATURA_JA_ENVIADA surfaces the server's own pt-BR message", async () => {
    mockPost.mockRejectedValueOnce(
      new ApiError(409, "fallback", {
        error: { code: "ASSINATURA_JA_ENVIADA", message: "Este contrato já está em assinatura." },
      }),
    );
    const { enviarParaAssinatura } = useContratoMutations("cli1");
    let captured: unknown;
    enviarParaAssinatura.mutate(
      {
        contratoId: "c1",
        versaoId: "v1",
        signatarios: [{ nome: "Ana", email: "a@x.com", cpf: "1", papel: "comprador" }],
      },
      { onError: (e) => (captured = e) },
    );
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    const err = captured as AssinaturaError;
    expect(err.code).toBe("ASSINATURA_JA_ENVIADA");
    expect(err.message).toBe("Este contrato já está em assinatura.");
  });

  it("§3.3 cancelarAssinatura POSTs only { motivo }", async () => {
    mockPost.mockResolvedValueOnce(assinatura({ status: "cancelado" }));
    const { cancelarAssinatura } = useContratoMutations("cli1");
    cancelarAssinatura.mutate({ contratoId: "c1", motivo: "Cliente desistiu" });
    await Promise.resolve();
    await Promise.resolve();
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli1/contratos/c1/assinatura/cancelar", {
      motivo: "Cliente desistiu",
    });
  });

  it("🔴 502 ASSINATURA_PROVEDOR_ERRO carries details.provedor_mensagem", async () => {
    mockPost.mockRejectedValueOnce(
      new ApiError(502, "fallback", {
        error: {
          code: "ASSINATURA_PROVEDOR_ERRO",
          message: "A plataforma de assinatura recusou o envio.",
          details: { provedor_mensagem: "signer email already used" },
        },
      }),
    );
    const { enviarParaAssinatura } = useContratoMutations("cli1");
    let captured: unknown;
    enviarParaAssinatura.mutate(
      {
        contratoId: "c1",
        versaoId: "v1",
        signatarios: [{ nome: "Ana", email: "a@x.com", cpf: "1", papel: "comprador" }],
      },
      { onError: (e) => (captured = e) },
    );
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    const err = captured as AssinaturaError;
    expect(err.details?.provedor_mensagem).toBe("signer email already used");
  });
});

describe("migration 157 — modalidade de assinatura", () => {
  function versao(over: Partial<VersaoOut> = {}): VersaoOut {
    return {
      id: "v1", nome_original: "c.pdf", mime_type: "application/pdf", tamanho_bytes: 1,
      tipo_documento: "contrato", enviado_por: null, created_at: "2026-09-20T00:00:00Z",
      numero: 1, rotulo: null, origem: "gerado", docx_disponivel: true,
      modalidade_assinatura: "fisica", ...over,
    };
  }
  function contrato(atual: VersaoOut | null): ContratoOut {
    return {
      id: "c1", atendimento_id: "a1", titulo: "t", modelo: "compra_venda", status: "rascunho",
      status_em: null, status_por: null, origem: "gerado", created_at: "2026-09-20T00:00:00Z",
      updated_at: null, versao_atual: atual, versoes: atual ? [atual] : [],
      assinatura_data: null, prazo_pendencias_dias: null, processo_legado: false,
      processo_legado_por: null, processo_legado_em: null, processo_legado_motivo: null,
      modalidade_assinatura: "fisica",
    };
  }

  it("versaoParaImpressao returns only a gerado rendering made as física", () => {
    expect(versaoParaImpressao(contrato(versao()))?.id).toBe("v1");
    expect(versaoParaImpressao(contrato(versao({ modalidade_assinatura: "digital" })))).toBeNull();
    expect(versaoParaImpressao(contrato(versao({ modalidade_assinatura: null })))).toBeNull();
    expect(versaoParaImpressao(contrato(versao({ origem: "assinado" })))).toBeNull();
    expect(versaoParaImpressao(contrato(null))).toBeNull();
  });

  it("the scanned copy must be a PDF", () => {
    expect(validateContratoAssinadoFile(new File(["%PDF"], "a.pdf"))).toBeNull();
    expect(validateContratoAssinadoFile(new File(["PK"], "a.docx"))).toContain("PDF");
  });

  it("marcarAssinadoFisico POSTs multipart to .../assinatura-fisica, with or without the scan", async () => {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response(JSON.stringify(contrato(versao())), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { marcarAssinadoFisico } = useContratoMutations("cli1") as unknown as {
      marcarAssinadoFisico: { _mutationFn: (v: unknown) => Promise<unknown> };
    };

    await marcarAssinadoFisico._mutationFn({ contratoId: "c1" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/clientes/cli1/contratos/c1/assinatura-fisica");
    expect(init.method).toBe("POST");
    expect((init.body as FormData).has("file")).toBe(false);

    const pdf = new File(["%PDF"], "assinado.pdf", { type: "application/pdf" });
    await marcarAssinadoFisico._mutationFn({ contratoId: "c1", file: pdf });
    const body = (fetchMock.mock.calls[1] as [string, RequestInit])[1].body as FormData;
    expect(body.get("file")).toBeInstanceOf(File);
    vi.unstubAllGlobals();
  });

  it("🔴 a typed refusal surfaces the server's own pt-BR message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code: "CONTRATO_NAO_E_FISICO", message: "Só um contrato de assinatura física..." } }),
          { status: 409 },
        ),
      ),
    );
    const { marcarAssinadoFisico } = useContratoMutations("cli1") as unknown as {
      marcarAssinadoFisico: { _mutationFn: (v: unknown) => Promise<unknown> };
    };
    await expect(marcarAssinadoFisico._mutationFn({ contratoId: "c1" })).rejects.toThrow(
      "Só um contrato de assinatura física...",
    );
    vi.unstubAllGlobals();
  });
});
