/**
 * useMatriculas — the extraction upload/list/delete hooks.
 *
 * Scope: the F2 additions (`codigo` filter on the list, `codigo` on upload,
 * `de-documento` transcription) plus the 409-delete-message contract
 * (`readableError` strips the `[status]` prefix so the toast reads the
 * server's own sentence). Mocks `@tanstack/react-query` entirely — same
 * pattern `useN8nWorkflows.test.ts` uses — so `mutate`/`queryFn` are called
 * directly with no QueryClientProvider needed.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockUpload, mockDelete, mockPost, invalidateQueriesMock, toastError, toastSuccess } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockUpload: vi.fn(),
    mockDelete: vi.fn(),
    mockPost: vi.fn(),
    invalidateQueriesMock: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
  }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, upload: mockUpload, delete: mockDelete, post: mockPost },
  useAuthStore: () => ({ user: { id: "u1" } }),
}));

vi.mock("sonner", () => ({
  toast: { error: toastError, success: toastSuccess },
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
            onError?.(err);
            opts?.onError?.(err);
          });
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  readableError,
  useCriarExtracaoDeDocumento,
  useDeleteExtracao,
  useMatriculaExtracoes,
  useUploadMatricula,
} from "./useMatriculas";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("readableError", () => {
  it("strips the seed api client's [<status>] prefix", () => {
    expect(readableError(new Error("[409] Extração vinculada a um contrato."))).toBe(
      "Extração vinculada a um contrato.",
    );
  });

  it("leaves an unprefixed message untouched", () => {
    expect(readableError(new Error("Servidor indisponivel"))).toBe("Servidor indisponivel");
  });
});

describe("useMatriculaExtracoes", () => {
  it("passes codigo/busca as GET params, unfiltered when omitted", async () => {
    mockGet.mockResolvedValue({ data: [] });
    const hook = useMatriculaExtracoes() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/extracoes", {
      codigo: undefined,
      busca: undefined,
    });
  });

  it("narrows to one imóvel's matrículas via codigo", async () => {
    mockGet.mockResolvedValue({ data: [] });
    const hook = useMatriculaExtracoes({ codigo: "ONE9001" }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/matriculas/extracoes", {
      codigo: "ONE9001",
      busca: undefined,
    });
  });
});

describe("useUploadMatricula", () => {
  it("accepts a bare File — every pre-F2 call site passes one", async () => {
    mockUpload.mockResolvedValue({ data: { id: "e1" } });
    const hook = useUploadMatricula() as any;
    const file = new File(["%PDF"], "m.pdf", { type: "application/pdf" });
    hook.mutate(file);
    await vi.waitFor(() => expect(mockUpload).toHaveBeenCalled());
    const formData = mockUpload.mock.calls[0][1] as FormData;
    expect(formData.get("file")).toBe(file);
    expect(formData.get("codigo")).toBeNull();
  });

  it("🔴 appends codigo to the multipart body when given an imóvel", async () => {
    mockUpload.mockResolvedValue({ data: { id: "e1" } });
    const hook = useUploadMatricula() as any;
    const file = new File(["%PDF"], "m.pdf", { type: "application/pdf" });
    hook.mutate({ file, codigo: "ONE9001" });
    await vi.waitFor(() => expect(mockUpload).toHaveBeenCalled());
    const formData = mockUpload.mock.calls[0][1] as FormData;
    expect(formData.get("codigo")).toBe("ONE9001");
  });
});

describe("useCriarExtracaoDeDocumento", () => {
  it("POSTs codigo + imovel_documento_id", async () => {
    mockPost.mockResolvedValue({ data: { id: "e2" } });
    const hook = useCriarExtracaoDeDocumento() as any;
    hook.mutate({ codigo: "ONE9001", imovelDocumentoId: "doc-1" });
    await vi.waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/api/matriculas/extracoes/de-documento", {
      codigo: "ONE9001",
      imovel_documento_id: "doc-1",
    });
  });
});

describe("useDeleteExtracao — 409 surfaces the server's own message", () => {
  it("🔴 shows the backend's detail, prefix stripped, when a contract quotes the extraction", async () => {
    mockDelete.mockRejectedValue(new Error("[409] Extração vinculada a um contrato."));
    const hook = useDeleteExtracao() as any;
    hook.mutate("extracao-9");
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Erro ao excluir", {
      description: "Extração vinculada a um contrato.",
    });
  });
});
