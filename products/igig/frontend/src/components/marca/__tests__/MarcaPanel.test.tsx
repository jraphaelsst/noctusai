/**
 * MarcaPanel — "Nome da marca" save-on-blur (achado 19).
 *
 * Clearing the field and blurring saves NOTHING (the guard requires a
 * non-empty, changed value) — but the input used to stay visually blank
 * forever, because its `key` only remounts on a CHANGED `marca.nome`. The
 * user sees "I erased the name" even though the server still has it.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { MarcaPanel } from "../MarcaPanel";
import type { Marca } from "@/hooks/useMarca";

const MARCA: Marca = {
  id: "m1", org_id: "o", cliente_id: "c1", nome: "Sol Pães", logo_url: null,
  paleta: [], tom_de_voz: null, termos_proibidos: null, nivel_formalidade: null,
  linhas_editoriais: [], personas: [],
};

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarcaPanel marca={MARCA} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MarcaPanel — Nome da marca", () => {
  it("saves a real change on blur", async () => {
    api.patch.mockResolvedValue({ ...MARCA, nome: "Sol Pães Novo" });
    renderPanel();
    const input = screen.getByLabelText("Nome da marca") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Sol Pães Novo" } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/api/marcas/m1", { nome: "Sol Pães Novo" }),
    );
  });

  it("puts the name BACK on screen when cleared — nothing was saved (achado 19)", () => {
    renderPanel();
    const input = screen.getByLabelText("Nome da marca") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(api.patch).not.toHaveBeenCalled();
    expect(input.value).toBe("Sol Pães");
  });

  it("does not call the API when blurring with the value unchanged", () => {
    renderPanel();
    const input = screen.getByLabelText("Nome da marca") as HTMLInputElement;
    fireEvent.blur(input);
    expect(api.patch).not.toHaveBeenCalled();
    expect(input.value).toBe("Sol Pães");
  });
});
