/** Library profile page: header, its Estruturas + videos, admin-only actions and the two-step delete. */
import { ConfirmProvider } from "@noctusai/lib/components";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = vi.hoisted(() => ({
  admin: vi.fn(),
  perfil: vi.fn(),
  videos: vi.fn(),
  estruturas: vi.fn(),
  sincronizar: vi.fn(),
  atualizar: vi.fn(),
  remover: vi.fn(),
}));
vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }) }));
vi.mock("@/hooks/geracao/useEstruturas", () => ({
  ESTRUTURAS_POR_PAGINA: 20,
  useEstruturasAdmin: () => m.admin(),
  useEstruturas: (...a: unknown[]) => m.estruturas(...a),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfilBiblioteca: () => m.perfil(),
  useViraisBiblioteca: (...a: unknown[]) => m.videos(...a),
  useViralDetalhe: () => ({ data: undefined, showSkeleton: false, isError: false, refetch: vi.fn() }),
  useSincronizarPerfil: () => ({ mutateAsync: (v: unknown) => m.sincronizar(v), isPending: false }),
  useAtualizarPerfil: () => ({ mutateAsync: (v: unknown) => m.atualizar(v), isPending: false }),
  useRemoverPerfil: () => ({ mutateAsync: (v: unknown) => m.remover(v), isPending: false }),
}));

import BibliotecaPerfil from "./BibliotecaPerfil";
import { resumo } from "@/test/estruturasFixtures";

const base = { isRefreshing: false, isError: false, error: null, failureCount: 0, isFetching: false, refetch: vi.fn() };
const perfil = (over: Record<string, unknown> = {}) => ({
  id: "p1", handle: "criador.exemplo", nome: "Criador Exemplo", foto_url: null, seguidores: 15300,
  status: "ativo", ultima_sync_em: "2026-11-10T00:00:00Z", monitorar: true, estruturas_total: 2, ingestao_ativa: true, ...over,
});
const viral = { id: "v1", codigo: 11, perfil: { id: "p1", handle: "criador.exemplo" }, thumbnail_url: null, permalink: "https://www.instagram.com/reel/AbC123/", publicado_em: "2026-10-01T00:00:00Z", views: null, likes: 10, comments: null, duracao_s: 30, score_viral: 1, e_viral: true, trecho: null };
const apiErr = (code: string, extra: Record<string, unknown> = {}) => Object.assign(new Error("[409] x"), { code, status: 409, field: (k: string) => extra[k] });

function renderPage() {
  rtl.render(
    <MemoryRouter initialEntries={["/media-creation/biblioteca/perfis/p1"]}>
      <ConfirmProvider>
        <Routes>
          <Route path="/media-creation/biblioteca/perfis/:perfilId" element={<BibliotecaPerfil />} />
          <Route path="/media-creation/biblioteca" element={<div>biblioteca</div>} />
        </Routes>
      </ConfirmProvider>
    </MemoryRouter>,
  );
}
const dialogo = async () => rtl.within(await rtl.screen.findByRole("dialog"));

beforeEach(() => {
  vi.clearAllMocks();
  m.admin.mockReturnValue({ data: false });
  m.perfil.mockReturnValue({ ...base, data: perfil(), showSkeleton: false });
  m.videos.mockReturnValue({ ...base, data: { items: [viral], total: 1, page: 1, filtro_automatico: false, ingestao_ativa: true }, showSkeleton: false });
  m.estruturas.mockReturnValue({ ...base, data: { items: [resumo()], total: 1 }, showSkeleton: false });
  m.sincronizar.mockResolvedValue(undefined);
  m.atualizar.mockResolvedValue(perfil());
  m.remover.mockResolvedValue(undefined);
});

describe("page", () => {
  it("shows the profile header, its Estruturas (pinned by perfil_id) and its videos", () => {
    renderPage();
    expect(rtl.screen.getByRole("heading", { name: "@criador.exemplo" })).toBeTruthy();
    expect(rtl.screen.getByText(/15,3K seguidores/)).toBeTruthy();
    expect(rtl.screen.getByText(/2 estruturas/)).toBeTruthy();
    expect(m.estruturas.mock.calls[0]![0].perfilId).toBe("p1");
    expect(rtl.screen.getByTestId("estrutura-card-e1")).toBeTruthy();
    expect(rtl.screen.getByTestId("viral-card-v1")).toBeTruthy();
  });

  it("a member sees no admin actions", () => {
    renderPage();
    expect(rtl.screen.queryByRole("group", { name: "Ações do administrador" })).toBeNull();
    expect(rtl.screen.queryByRole("button", { name: "Sincronizar agora" })).toBeNull();
    expect(rtl.screen.queryByLabelText("Monitorar novos vídeos")).toBeNull();
  });

  it("a library-only profile says so, and an unknown count is '—', never 0", () => {
    m.perfil.mockReturnValue({ ...base, data: perfil({ monitorar: false, estruturas_total: undefined }) });
    renderPage();
    expect(rtl.screen.getByText("Somente biblioteca")).toBeTruthy();
    expect(rtl.screen.getByText(/— estruturas/)).toBeTruthy();
  });

  it("states: skeleton, 404, retryable error, videos error, no videos", () => {
    m.perfil.mockReturnValue({ ...base, data: undefined, showSkeleton: true });
    renderPage();
    expect(rtl.screen.getByLabelText("Carregando perfil")).toBeTruthy();
    rtl.cleanup();
    m.perfil.mockReturnValue({ ...base, data: undefined, isError: true, error: Object.assign(new Error("x"), { status: 404 }) });
    renderPage();
    expect(rtl.screen.getByText("Perfil não encontrado")).toBeTruthy();
    rtl.cleanup();
    m.perfil.mockReturnValue({ ...base, data: undefined, isError: true, error: new Error("boom") });
    renderPage();
    expect(rtl.screen.getByRole("button", { name: /Tentar novamente/ })).toBeTruthy();
    rtl.cleanup();
    m.perfil.mockReturnValue({ ...base, data: perfil({ monitorar: false }) });
    m.videos.mockReturnValue({ ...base, data: { items: [], total: 0 }, showSkeleton: false });
    renderPage();
    expect(rtl.screen.getByText(/Nenhum vídeo deste perfil/)).toBeTruthy();
    expect(rtl.screen.getByText(/os vídeos entram por link/)).toBeTruthy();
  });
});

describe("admin actions", () => {
  beforeEach(() => m.admin.mockReturnValue({ data: true }));

  it("sync, pause/resume and the monitorar switch call the write hooks and say what happened", async () => {
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Sincronizar agora" }));
    await rtl.waitFor(() => expect(m.sincronizar).toHaveBeenCalledWith("p1"));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Pausar" }));
    await rtl.waitFor(() => expect(m.atualizar).toHaveBeenCalledWith({ id: "p1", status: "pausado" }));
    await userEvent.click(rtl.screen.getByLabelText("Monitorar novos vídeos"));
    await rtl.waitFor(() => expect(m.atualizar).toHaveBeenLastCalledWith({ id: "p1", monitorar: false }));
    expect(toast.success).toHaveBeenCalledWith("Monitoramento desligado.");
  });

  it("a refused action is a toast with the server's pt-BR sentence", async () => {
    m.sincronizar.mockRejectedValueOnce(Object.assign(new Error("x"), { status: 403 }));
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Sincronizar agora" }));
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Somente administradores da plataforma podem fazer isso."));
  });

  it("delete: confirm → 409 perfil_com_estruturas → second, explicit confirm → re-sends with apagar_estruturas", async () => {
    m.remover.mockRejectedValueOnce(apiErr("perfil_com_estruturas", { estruturas_total: 4 })).mockResolvedValueOnce(undefined);
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Excluir" }));
    const segundo = await dialogo();
    expect(segundo.getByText(/Este perfil tem 4 estruturas/)).toBeTruthy();
    await userEvent.click(segundo.getByRole("button", { name: "Apagar perfil e estruturas" }));
    await rtl.waitFor(() => expect(m.remover).toHaveBeenCalledTimes(2));
    expect(m.remover.mock.calls[0]![0]).toEqual({ id: "p1" });
    expect(m.remover.mock.calls[1]![0]).toEqual({ id: "p1", apagar_estruturas: true });
    expect(await rtl.screen.findByText("biblioteca")).toBeTruthy(); // navigated away
  });

  it("declining the second confirmation keeps the profile", async () => {
    m.remover.mockRejectedValueOnce(apiErr("perfil_com_estruturas", { estruturas_total: 1 }));
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Excluir" }));
    await userEvent.click((await dialogo()).getByRole("button", { name: "Cancelar" }));
    expect(m.remover).toHaveBeenCalledTimes(1);
    expect(rtl.screen.getByRole("heading", { name: "@criador.exemplo" })).toBeTruthy();
  });
});
