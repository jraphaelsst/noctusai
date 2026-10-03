/**
 * useContratoAditivos — the routes and wire shapes of
 * contrato-aditivos-CONTRACT §2, exercised through the query/mutation
 * FUNCTIONS (react-query mocked, same pattern as `useContratos.test.ts`).
 * Synthetic ids only.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const { mockGet, mockPost, mockPatch, invalidateQueriesMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled, queryKey }: any) => ({
    data: undefined,
    _queryFn: queryFn,
    _enabled: enabled,
    _queryKey: queryKey,
  }));
  const useMutation = vi.fn(({ mutationFn, onSuccess }: any) => ({
    mutateAsync: async (vars: unknown) => {
      const r = await mutationFn(vars);
      await onSuccess?.(r, vars);
      return r;
    },
  }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  aditivoDomId,
  rotuloAditivo,
  useAditivoGeracao,
  useAditivoMutations,
  useAditivos,
} from "./useContratoAditivos";
import { ContratoGeracaoError, contratoAdmiteAditivo, type ContratoOut } from "./useContratos";

const BASE = "/api/clientes/cl1/contratos/c1/aditivos";

beforeEach(() => vi.clearAllMocks());

describe("useAditivos / useAditivoGeracao", () => {
  it("GETs the list lazily, nested under the contratos key", async () => {
    mockGet.mockResolvedValue({ aditivos: [{ id: "ad1" }] });
    const fechado = useAditivos("cl1", "c1", false) as any;
    expect(fechado._enabled).toBe(false);
    const aberto = useAditivos("cl1", "c1", true) as any;
    expect(aberto._enabled).toBe(true);
    expect(aberto._queryKey).toEqual(["sw", "clientes", "cl1", "contratos", "c1", "aditivos"]);
    expect(await aberto._queryFn()).toEqual([{ id: "ad1" }]);
    expect(mockGet).toHaveBeenCalledWith(BASE);
  });

  it("GETs the readiness of one aditivo", async () => {
    mockGet.mockResolvedValue({ pronto: false });
    const q = useAditivoGeracao("cl1", "c1", "ad1", true) as any;
    await q._queryFn();
    expect(mockGet).toHaveBeenCalledWith(`${BASE}/ad1/geracao`);
  });
});

describe("useAditivoMutations", () => {
  it("creates, patches, approves — and invalidates the aditivos list", async () => {
    mockPost.mockResolvedValue({ id: "ad1" });
    mockPatch.mockResolvedValue({ id: "ad1" });
    const m = useAditivoMutations("cl1", "c1") as any;

    await m.criar.mutateAsync({ estilo: "formal" });
    expect(mockPost).toHaveBeenCalledWith(BASE, { estilo: "formal" });

    await m.atualizar.mutateAsync({ aditivoId: "ad1", patch: { status: "em_revisao" } });
    expect(mockPatch).toHaveBeenCalledWith(`${BASE}/ad1`, { status: "em_revisao" });

    await m.aprovarRevisaoJuridica.mutateAsync({ aditivoId: "ad1", versaoId: "v1" });
    expect(mockPost).toHaveBeenCalledWith(`${BASE}/ad1/versoes/v1/revisao-juridica`, {});

    for (const [arg] of invalidateQueriesMock.mock.calls) {
      expect(arg.queryKey).toEqual(["sw", "clientes", "cl1", "contratos", "c1", "aditivos"]);
    }
    expect(invalidateQueriesMock).toHaveBeenCalledTimes(3);
  });

  it("mints a version URL (docx / impressão only when asked)", async () => {
    mockGet.mockResolvedValue({ url: "https://example.invalid/x", expires_at: "" });
    const m = useAditivoMutations("cl1", "c1") as any;
    await m.getUrl.mutateAsync({ aditivoId: "ad1", versaoId: "v1" });
    expect(mockGet).toHaveBeenLastCalledWith(`${BASE}/ad1/versoes/v1/url?intent=view`);
    await m.getUrl.mutateAsync({ aditivoId: "ad1", versaoId: "v1", intent: "download", formato: "docx" });
    expect(mockGet).toHaveBeenLastCalledWith(`${BASE}/ad1/versoes/v1/url?intent=download&formato=docx`);
    await m.getUrl.mutateAsync({ aditivoId: "ad1", versaoId: "v1", intent: "download", impressao: true });
    expect(mockGet).toHaveBeenLastCalledWith(`${BASE}/ad1/versoes/v1/url?intent=download&impressao=true`);
  });

  it("🔴 gerar's 400 ADITIVO_INCOMPLETO arrives as a ContratoGeracaoError with its details", async () => {
    const details = { faltando: [{ campo: "aditivo.alteracoes", rotulo: "Alterações", onde: "contrato", parte_id: null }], bloqueios: [] };
    mockPost.mockRejectedValue(
      new ApiError(400, "O aditivo não pode ser gerado", {
        error: { code: "ADITIVO_INCOMPLETO", message: "O aditivo não pode ser gerado.", details },
      }),
    );
    const m = useAditivoMutations("cl1", "c1") as any;
    const err = await m.gerar.mutateAsync({ aditivoId: "ad1" }).catch((e: unknown) => e);
    expect(mockPost).toHaveBeenCalledWith(`${BASE}/ad1/gerar`, {});
    expect(err).toBeInstanceOf(ContratoGeracaoError);
    expect((err as ContratoGeracaoError).code).toBe("ADITIVO_INCOMPLETO");
    expect((err as ContratoGeracaoError).message).toBe("O aditivo não pode ser gerado.");
    expect((err as ContratoGeracaoError).details?.faltando?.[0].campo).toBe("aditivo.alteracoes");
  });

  it("gerar sends the chosen date", async () => {
    mockPost.mockResolvedValue({ versao: {}, avisos: [] });
    const m = useAditivoMutations("cl1", "c1") as any;
    await m.gerar.mutateAsync({ aditivoId: "ad1", assinaturaData: "2026-09-30" });
    expect(mockPost).toHaveBeenCalledWith(`${BASE}/ad1/gerar`, { assinatura_data: "2026-09-30" });
  });
});

describe("helpers", () => {
  it("names aditivos and their DOM target", () => {
    expect(rotuloAditivo(1)).toBe("Primeiro aditivo");
    expect(rotuloAditivo(3)).toBe("Terceiro aditivo");
    expect(rotuloAditivo(11)).toBe("11º aditivo");
    expect(aditivoDomId("ad1")).toBe("aditivo-ad1");
  });

  it("a contract admits an aditivo when signed or dated — never when cancelled", () => {
    const c = (over: Partial<ContratoOut>) => ({ status: "rascunho", assinatura_data: null, ...over }) as ContratoOut;
    expect(contratoAdmiteAditivo(c({ status: "assinado" }))).toBe(true);
    expect(contratoAdmiteAditivo(c({ assinatura_data: "2026-09-01" }))).toBe(true);
    expect(contratoAdmiteAditivo(c({}))).toBe(false);
    expect(contratoAdmiteAditivo(c({ status: "cancelado", assinatura_data: "2026-09-01" }))).toBe(false);
  });
});
