/**
 * useImovelDocumentoMutations — the upload race fix + the re-read mutation.
 *
 * P1/883 (2026-09-28): the document list relied on `invalidateQueries`
 * alone after an upload's POST resolved, which races its own refetch
 * against whatever else touches the same query key — in practice the new
 * row often did not show until a reload, or a PREVIOUS upload's row was
 * still the one visible. The fix is an OPTIMISTIC row: present the instant
 * `mutate` is called, reconciled with the real row (or rolled back) once
 * the request settles — no dependence on a GET winning a race it started.
 *
 * A REAL `QueryClient`, same reason `useImovelDados.extracaoPolling.test
 * .tsx` gives: this is cache-timing behaviour a mocked `useQuery` (a static
 * return, no re-render on data change) cannot exercise.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "tok123" } } }),
    },
  },
}));

import { useImovelDocumentoMutations } from "./useImovelDados";
import type { ImovelDocumento } from "./useImovelDados";

const CODIGO = "AP1234";
const DOCUMENTOS_KEY = (codigo: string) => ["sw", "imovel-dados", codigo, "documentos"];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function makeDoc(over: Partial<ImovelDocumento> = {}): ImovelDocumento {
  return {
    id: "real-1",
    codigo: CODIGO,
    nome_original: "matricula.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 100,
    tipo_documento: "matricula",
    enviado_por: null,
    created_at: "2026-01-01T00:00:00+00:00",
    extracao_status: "pendente",
    extracao_matricula: null,
    extracao_confianca: null,
    extracao_rotulo: null,
    extracao_erro: null,
    ...over,
  };
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

describe("useImovelDocumentoMutations — upload (deterministic list)", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    qc.clear();
    vi.unstubAllGlobals();
  });

  it("🔴 the new row is visible the INSTANT mutate is called — before the network resolves", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    (fetch as unknown as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    qc.setQueryData(DOCUMENTOS_KEY(CODIGO), []);

    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });

    const file = new File(["x"], "matricula.pdf", { type: "application/pdf" });
    act(() => {
      result.current.upload.mutate({ file, tipoDocumento: "matricula" });
    });

    await waitFor(() => {
      const list = qc.getQueryData<ImovelDocumento[]>(DOCUMENTOS_KEY(CODIGO));
      expect(list).toHaveLength(1);
      expect(list?.[0].nome_original).toBe("matricula.pdf");
      expect(list?.[0].tipo_documento).toBe("matricula");
    });

    resolveFetch(jsonResponse(makeDoc()));
    await waitFor(() => expect(result.current.upload.isSuccess).toBe(true));
  });

  it("replaces the optimistic row with the real one on success — never a duplicate", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDoc({ id: "real-1" })),
    );
    qc.setQueryData(DOCUMENTOS_KEY(CODIGO), []);

    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });
    const file = new File(["x"], "matricula.pdf", { type: "application/pdf" });
    await act(async () => {
      await result.current.upload.mutateAsync({ file, tipoDocumento: "matricula" });
    });

    const list = qc.getQueryData<ImovelDocumento[]>(DOCUMENTOS_KEY(CODIGO));
    expect(list).toHaveLength(1);
    expect(list?.[0].id).toBe("real-1");
  });

  it("🔴 an upload right after a previous one is visible too — the 'lags one upload behind' bug", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jsonResponse(makeDoc({ id: "real-1", nome_original: "a.pdf" })))
      .mockResolvedValueOnce(
        jsonResponse(makeDoc({ id: "real-2", nome_original: "b.pdf" })),
      );
    qc.setQueryData(DOCUMENTOS_KEY(CODIGO), []);

    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      await result.current.upload.mutateAsync({
        file: new File(["a"], "a.pdf", { type: "application/pdf" }),
        tipoDocumento: "matricula",
      });
    });
    await act(async () => {
      await result.current.upload.mutateAsync({
        file: new File(["b"], "b.pdf", { type: "application/pdf" }),
        tipoDocumento: "guia_iptu",
      });
    });

    const names = qc
      .getQueryData<ImovelDocumento[]>(DOCUMENTOS_KEY(CODIGO))
      ?.map((d) => d.nome_original);
    expect(names).toContain("a.pdf");
    expect(names).toContain("b.pdf");
  });

  it("rolls back the optimistic row when the upload fails", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { message: "arquivo grande demais" } }, false, 400),
    );
    qc.setQueryData(DOCUMENTOS_KEY(CODIGO), []);

    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });
    const file = new File(["x"], "matricula.pdf", { type: "application/pdf" });
    await act(async () => {
      await result.current.upload.mutateAsync({ file, tipoDocumento: "matricula" }).catch(() => {});
    });

    expect(qc.getQueryData<ImovelDocumento[]>(DOCUMENTOS_KEY(CODIGO))).toEqual([]);
  });
});

describe("useImovelDocumentoMutations — reextrair", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockPost.mockReset();
  });

  afterEach(() => qc.clear());

  it("POSTs to the /extrair endpoint and invalidates the documentos list", async () => {
    mockPost.mockResolvedValue(makeDoc({ id: "d1", extracao_status: "pendente" }));
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      await result.current.reextrair.mutateAsync("d1");
    });

    expect(mockPost).toHaveBeenCalledWith(
      `/api/imoveis/${CODIGO}/documentos/d1/extrair`,
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: DOCUMENTOS_KEY(CODIGO) }),
    );
  });

  it("uses the document's own código in the path when given one (linked imóvel)", async () => {
    mockPost.mockResolvedValue(makeDoc({ id: "dm" }));
    const { result } = renderHook(() => useImovelDocumentoMutations(CODIGO), {
      wrapper: makeWrapper(qc),
    });
    await act(async () => {
      await result.current.reextrair.mutateAsync({ documentoId: "dm", codigo: "SW-0001" });
    });
    expect(mockPost).toHaveBeenCalledWith("/api/imoveis/SW-0001/documentos/dm/extrair");
  });
});
