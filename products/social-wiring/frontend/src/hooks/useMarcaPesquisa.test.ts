import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MARCA_STORAGE_KEY, useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import type { Marca } from "@/hooks/useMarcas";

const mk = (id: string): Marca => ({ id, name: id, slug: id } as Marca);
const marcas = [mk("a"), mk("b")];

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("useMarcaPesquisa", () => {
  it("falls back to the first marca when nothing is stored", () => {
    const { result } = renderHook(() => useMarcaPesquisa(marcas));
    expect(result.current.marcaId).toBe("a");
  });

  it("restores a stored marca and ignores a stale id", () => {
    window.localStorage.setItem(MARCA_STORAGE_KEY, "b");
    expect(renderHook(() => useMarcaPesquisa(marcas)).result.current.marcaId).toBe("b");
    window.localStorage.setItem(MARCA_STORAGE_KEY, "gone");
    expect(renderHook(() => useMarcaPesquisa(marcas)).result.current.marcaId).toBe("a");
  });

  it("persists the choice", () => {
    const { result } = renderHook(() => useMarcaPesquisa(marcas));
    act(() => result.current.escolherMarca("b"));
    expect(result.current.marcaId).toBe("b");
    expect(window.localStorage.getItem(MARCA_STORAGE_KEY)).toBe("b");
  });

  it("survives a throwing localStorage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const { result } = renderHook(() => useMarcaPesquisa(marcas));
    expect(result.current.marcaId).toBe("a");
    act(() => result.current.escolherMarca("b"));
    expect(result.current.marcaId).toBe("b");
  });
});
