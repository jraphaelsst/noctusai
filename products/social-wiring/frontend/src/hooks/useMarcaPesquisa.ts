/**
 * Selected marca for the Pesquisa surfaces, remembered in localStorage
 * (`sw.pesquisa.marca`). Every storage access is try/catch'd: private mode /
 * quota just means the choice is not remembered. A stored id that no longer
 * exists in `marcas` falls back to the first marca.
 */
import { useState } from "react";

import type { Marca } from "@/hooks/useMarcas";

export const MARCA_STORAGE_KEY = "sw.pesquisa.marca";

export function lerMarcaSalva(): string | null {
  try {
    return window.localStorage.getItem(MARCA_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function salvarMarca(id: string) {
  try {
    window.localStorage.setItem(MARCA_STORAGE_KEY, id);
  } catch {
    // storage unavailable (private mode / quota): the switcher just won't be remembered.
  }
}

export function useMarcaPesquisa(marcas: Marca[]) {
  const [marcaSalva, setMarcaSalva] = useState<string | null>(() => lerMarcaSalva());
  const marcaId = marcas.find((m) => m.id === marcaSalva)?.id ?? marcas[0]?.id ?? null;
  const marca = marcas.find((m) => m.id === marcaId) ?? null;

  function escolherMarca(id: string) {
    setMarcaSalva(id);
    salvarMarca(id);
  }

  return { marcaId, marca, escolherMarca };
}
