/** useImovelManual — request shape + cache invalidation (list/filtros AND the busca pickers read). */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { post, patch } = vi.hoisted(() => ({ post: vi.fn(), patch: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { post, patch, get: vi.fn() } }));

import {
  driveUrlValida,
  useAtualizarImovelManual,
  useAtualizarReferencias,
  useCriarImovelManual,
} from "./useImovelManual";

function setup() {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}
const keys = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.map((c) =>
    JSON.stringify((c[0] as { queryKey: unknown }).queryKey),
  );

beforeEach(() => {
  post.mockReset();
  patch.mockReset();
});

describe("useImovelManual", () => {
  it("create POSTs /manuais, tolerates decimal strings, invalidates imoveis + imoveisBusca", async () => {
    post.mockResolvedValue({ codigo: "SW-0001", valor_venda: "1250000.00" });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCriarImovelManual(), { wrapper });
    const body = {
      titulo: "T",
      endereco: {
        logradouro: "R",
        numero: "1",
        bairro: "B",
        cidade: "C",
        uf: "SP",
      },
    };
    const res = await result.current.mutateAsync(body);

    expect(post).toHaveBeenCalledWith("/api/imoveis/manuais", body);
    expect(res.valor_venda).toBe(1250000);
    await waitFor(() => expect(keys(spy)).toContain('["sw","imoveis"]'));
    expect(keys(spy)).toContain('["sw","cardHub","imoveisBusca"]');
  });

  it("edit PATCHes /manuais/{codigo}", async () => {
    patch.mockResolvedValue({ codigo: "SW-0001" });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAtualizarImovelManual("SW-0001"), {
      wrapper,
    });
    await result.current.mutateAsync({ titulo: "N" });
    expect(patch).toHaveBeenCalledWith("/api/imoveis/manuais/SW-0001", {
      titulo: "N",
    });
    await waitFor(() => expect(keys(spy)).toContain('["sw","imoveis"]'));
  });

  it("referências PATCH /{codigo}/referencias works for any imóvel", async () => {
    patch.mockResolvedValue({});
    const { wrapper } = setup();
    const { result } = renderHook(() => useAtualizarReferencias("ONE1"), {
      wrapper,
    });
    await result.current.mutateAsync({ processo_atual_numero: "9" });
    expect(patch).toHaveBeenCalledWith("/api/imoveis/ONE1/referencias", {
      processo_atual_numero: "9",
    });
  });

  it("driveUrlValida accepts folder links only", () => {
    expect(
      driveUrlValida("https://drive.google.com/drive/folders/1abc_D-9"),
    ).toBe(true);
    expect(
      driveUrlValida("https://drive.google.com/drive/u/0/folders/1abc"),
    ).toBe(true);
    expect(driveUrlValida("https://drive.google.com/file/d/1abc/view")).toBe(
      false,
    );
    expect(driveUrlValida("http://drive.google.com/drive/folders/1abc")).toBe(
      false,
    );
  });
});
