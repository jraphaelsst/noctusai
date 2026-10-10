/**
 * MeuPerfil.test.tsx — max-3 nichos/profissões, incomplete-profile "Atenção" modal
 * (Cancelar / Continuar), save payload, four states. API hooks mocked; no network.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MeuPerfilDefault, { MeuPerfil, perfilIncompleto } from "./MeuPerfil";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = vi.hoisted(() => ({
  marcas: vi.fn(),
  perfil: vi.fn(),
  tax: vi.fn(),
  contas: vi.fn(),
  salvar: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/useIntegrationAccounts", () => ({ useIntegrationAccounts: () => m.contas() }));
vi.mock("@/hooks/geracao/useTaxonomias", () => ({ useTaxonomias: () => m.tax() }));
vi.mock("@/hooks/geracao/usePerfilCriacao", () => ({
  usePerfilCriacao: (id: unknown) => m.perfil(id),
  useSalvarPerfilCriacao: () => ({ mutateAsync: m.salvar, isPending: false }),
}));

const q = (data: unknown, over: Record<string, unknown> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isPending: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

const TAX = {
  nichos: [1, 2, 3, 4].map((id) => ({ id, nome: `Nicho ${id}` })),
  profissoes: [10, 11, 12, 13].map((id) => ({ id, nome: `Profissão ${id}` })),
  formatos: [],
  gatilhos: [],
  tons: [],
};
const perfil = (over: Record<string, unknown> = {}) => ({
  marca_id: "m1",
  bio: "",
  nichos: [],
  profissoes: [],
  apresentacao_magnetica: "",
  ctas: "",
  updated_at: null,
  ...over,
});

function renderPage() {
  const user = userEvent.setup();
  const r = rtl.render(
    <MemoryRouter>
      <MeuPerfil />
    </MemoryRouter>,
  );
  return { ...r, user };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  m.marcas.mockReturnValue({ data: [{ id: "m1", name: "Marca Um" }], isPending: false, isError: false });
  m.perfil.mockReturnValue(q(perfil()));
  m.tax.mockReturnValue(q(TAX));
  m.contas.mockReturnValue(q([]));
  m.salvar.mockResolvedValue(perfil());
});

describe("perfilIncompleto", () => {
  it("applies CoreStudio's bio XOR (nichos ∧ profissões) rule", () => {
    expect(perfilIncompleto({ bio: "", nichos: [], profissoes: [] })).toBe(false);
    expect(perfilIncompleto({ bio: "x", nichos: [1], profissoes: [2] })).toBe(false);
    expect(perfilIncompleto({ bio: "x", nichos: [1], profissoes: [] })).toBe(true);
    expect(perfilIncompleto({ bio: "x", nichos: [], profissoes: [] })).toBe(true);
    expect(perfilIncompleto({ bio: "", nichos: [1], profissoes: [2] })).toBe(true);
    expect(perfilIncompleto({ bio: "  ", nichos: [1], profissoes: [2] })).toBe(true);
  });
});

describe("MeuPerfil", () => {
  it("exports the page as default and named", () => {
    expect(MeuPerfilDefault).toBe(MeuPerfil);
  });

  it("limits nichos to 3 and shows the CoreStudio error", async () => {
    const { user } = renderPage();
    await user.click(rtl.screen.getByTestId("taxon-nichos"));
    const box = (n: string) => rtl.screen.getByRole("checkbox", { name: n }) as HTMLButtonElement;
    expect(rtl.screen.getByText("Selecione até 3 nichos")).toBeTruthy();
    await user.click(box("Nicho 1"));
    await user.click(box("Nicho 2"));
    await user.click(box("Nicho 3"));
    expect(rtl.screen.getByText("Máximo de 3 nichos permitidos")).toBeTruthy();
    expect(box("Nicho 4").disabled).toBe(true);
    await user.click(box("Nicho 1"));
    expect(box("Nicho 4").disabled).toBe(false);
  });

  it("limits profissões to 3", async () => {
    const { user } = renderPage();
    await user.click(rtl.screen.getByTestId("taxon-profissoes"));
    for (const n of ["Profissão 10", "Profissão 11", "Profissão 12"]) {
      await user.click(rtl.screen.getByRole("checkbox", { name: n }));
    }
    expect(rtl.screen.getByText("Máximo de 3 profissões permitidos")).toBeTruthy();
    expect((rtl.screen.getByRole("checkbox", { name: "Profissão 13" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves a complete profile straight away with the full payload", async () => {
    const { user } = renderPage();
    await user.click(rtl.screen.getByTestId("taxon-nichos"));
    await user.click(rtl.screen.getByRole("checkbox", { name: "Nicho 2" }));
    await user.keyboard("{Escape}");
    await user.click(rtl.screen.getByTestId("taxon-profissoes"));
    await user.click(rtl.screen.getByRole("checkbox", { name: "Profissão 11" }));
    await user.keyboard("{Escape}");
    await user.type(rtl.screen.getByLabelText("Bio"), "Minha bio");
    await user.type(rtl.screen.getByLabelText("CTAs"), "Siga");
    await user.click(rtl.screen.getByRole("button", { name: "Atualizar" }));
    expect(rtl.screen.queryByText("Atenção")).toBeNull();
    await rtl.waitFor(() =>
      expect(m.salvar).toHaveBeenCalledWith({
        marca_id: "m1",
        bio: "Minha bio",
        nichos: [2],
        profissoes: [11],
        apresentacao_magnetica: "",
        ctas: "Siga",
      }),
    );
  });

  it("asks for confirmation on an incomplete profile: Cancelar does not save, Continuar does", async () => {
    const { user } = renderPage();
    await user.type(rtl.screen.getByLabelText("Bio"), "só a bio");
    await user.click(rtl.screen.getByRole("button", { name: "Atualizar" }));
    expect(await rtl.screen.findByText("Atenção")).toBeTruthy();
    await user.click(rtl.screen.getByRole("button", { name: "Cancelar" }));
    expect(m.salvar).not.toHaveBeenCalled();

    await user.click(rtl.screen.getByRole("button", { name: "Atualizar" }));
    await user.click(await rtl.screen.findByRole("button", { name: "Continuar" }));
    await rtl.waitFor(() => expect(m.salvar).toHaveBeenCalledTimes(1));
  });

  it("shows the bio template in the help popover", async () => {
    const { user } = renderPage();
    await user.click(rtl.screen.getByLabelText("Modelo de Bio"));
    expect(await rtl.screen.findByText(/^Eu sou \(Nome\), Sou \(Profissão\)/)).toBeTruthy();
  });

  it("renders the Instagram card from the marca's connections", () => {
    m.contas.mockReturnValue(
      q([
        { id: "a1", provider: "instagram", account_label: "@marca" },
        { id: "a2", provider: "meta", account_label: "FB" },
      ]),
    );
    renderPage();
    expect(rtl.screen.getByText("@marca")).toBeTruthy();
    expect(rtl.screen.getByText(/Conexão Meta \(Facebook Login\) disponível/)).toBeTruthy();
  });

  it("warns when no Meta connection exists", () => {
    renderPage();
    expect(rtl.screen.getByText(/Nenhuma conta Meta \(Facebook Login\) conectada/)).toBeTruthy();
  });

  it("shows skeleton, error (retry) and empty-marca states; keeps the form while refreshing", async () => {
    m.perfil.mockReturnValue(q(undefined, { showSkeleton: true }));
    let r = renderPage();
    expect(rtl.screen.getByTestId("perfil-skeleton")).toBeTruthy();
    r.unmount();

    const refetch = vi.fn();
    m.perfil.mockReturnValue(q(undefined, { isError: true, refetch }));
    r = renderPage();
    await r.user.click(rtl.screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
    r.unmount();

    m.perfil.mockReturnValue(q(perfil(), { isRefreshing: true }));
    r = renderPage();
    expect(rtl.screen.getByText("Atualizando…")).toBeTruthy();
    expect(rtl.screen.getByLabelText("Bio")).toBeTruthy();
    r.unmount();

    m.marcas.mockReturnValue({ data: [], isPending: false, isError: false });
    renderPage();
    expect(rtl.screen.getByText(/Cadastre uma marca em Clientes/)).toBeTruthy();
  });
});
