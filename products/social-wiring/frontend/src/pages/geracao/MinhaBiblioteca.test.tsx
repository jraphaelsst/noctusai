/** Minha Biblioteca: live handle check states, references table, honest banner. */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MinhaBiblioteca from "./MinhaBiblioteca";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({
  perfis: vi.fn(),
  refs: vi.fn(),
  verificar: vi.fn(),
  contas: vi.fn(),
  solicitar: vi.fn(),
  removerRef: vi.fn(),
  criar: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfisMonitorados: () => m.perfis(),
  useReferencias: () => m.refs(),
  useVerificarPerfil: (h: string) => m.verificar(h),
  useContasDescoberta: () => m.contas(),
  useSolicitarPerfil: () => ({ mutateAsync: m.solicitar, isPending: false }),
  useCriarReferencias: () => ({ mutateAsync: m.criar, isPending: false }),
  useSincronizarPerfil: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAtualizarPerfil: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverPerfil: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverReferencia: () => ({ mutateAsync: m.removerRef, isPending: false }),
}));

const ok = <T,>(data: T) => ({ data, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn() });

const perfil = (over: Partial<any> = {}) => ({
  id: "p1",
  handle: "fulano",
  status: "aguardando",
  erro_mensagem: null,
  ultima_sync_em: null,
  virais: 0,
  ingestao_ativa: false,
  ...over,
});

function renderPage() {
  return rtl.render(
    <MemoryRouter>
      <MinhaBiblioteca />
    </MemoryRouter>,
  );
}

async function abrirSolicitar() {
  await userEvent.click(rtl.screen.getByRole("tab", { name: "Solicitar Perfil" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  m.perfis.mockReturnValue(ok([perfil()]));
  m.refs.mockReturnValue(
    ok([
      {
        id: "r1",
        modo: "perfil",
        perfil: perfil(),
        viral: null,
        auto_atualizar: true,
        posts_ate: null,
        updated_at: "2026-10-09T10:00:00Z",
      },
    ]),
  );
  m.verificar.mockReturnValue({ data: undefined, isFetching: false, isError: false });
  m.contas.mockReturnValue({ data: [] });
  m.solicitar.mockResolvedValue(perfil());
  m.removerRef.mockResolvedValue(undefined);
});

describe("Minha Biblioteca", () => {
  it("says monitoring is not activated when ingestion is off", () => {
    renderPage();
    expect(rtl.screen.getByText(/Monitoramento ainda não ativado/)).toBeTruthy();
    expect(rtl.screen.getAllByText("Aguardando").length).toBeGreaterThan(0);
  });

  it("no banner once ingestion is active", () => {
    m.perfis.mockReturnValue(ok([perfil({ status: "ativo", ultima_sync_em: "2026-10-01T00:00:00Z", virais: 5, ingestao_ativa: true })]));
    renderPage();
    expect(rtl.screen.queryByText(/Monitoramento ainda não ativado/)).toBeNull();
  });

  it("shows the references table with Auto badge and 'Todos'", () => {
    renderPage();
    expect(rtl.screen.getByText("Auto")).toBeTruthy();
    expect(rtl.screen.getByText("Todos")).toBeTruthy();
  });

  it("removing a reference needs the confirm", async () => {
    renderPage();
    const tabela = rtl.screen.getByText("Minhas referências").closest("section")!;
    await userEvent.click(rtl.within(tabela).getByRole("button", { name: "Remover" }));
    expect(await rtl.screen.findByText("Remover referência")).toBeTruthy();
    expect(m.removerRef).not.toHaveBeenCalled();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Remover", hidden: false }));
    await rtl.waitFor(() => expect(m.removerRef).toHaveBeenCalledWith("r1"));
  });

  it("error on references offers Tentar novamente", () => {
    m.refs.mockReturnValue({ data: undefined, showSkeleton: false, isRefreshing: false, isError: true, refetch: vi.fn() });
    renderPage();
    expect(rtl.screen.getByText(/Não foi possível carregar as referências/)).toBeTruthy();
  });
});

describe("Solicitar Perfil live check", () => {
  it("rejects a post link without calling the check", async () => {
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "https://instagram.com/reel/abc/");
    expect(await rtl.screen.findByText(/não o link de um post/)).toBeTruthy();
    expect(m.verificar).not.toHaveBeenCalledWith("abc");
    expect((rtl.screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it.each([
    ["ja_monitorado", "⚠️ Este perfil já está na biblioteca (monitorado)"],
    ["na_minha_biblioteca", "⚠️ Este perfil já está na sua biblioteca."],
    ["sem_conta_descoberta", "✗ Nenhuma conta Meta (Facebook Login) conectada — conecte em Conexões › Marcas para monitorar perfis."],
  ])("status %s blocks submit with its message", async (status, texto) => {
    m.verificar.mockImplementation((h: string) => ({ data: h ? { status } : undefined, isFetching: false, isError: false }));
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@novo");
    expect(await rtl.screen.findByText(texto)).toBeTruthy();
    expect((rtl.screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("valid username enables Enviar and posts the normalized handle", async () => {
    m.verificar.mockImplementation((h: string) => ({
      data: h ? { status: "disponivel" } : undefined,
      isFetching: false,
      isError: false,
    }));
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@Novo.Perfil");
    expect(await rtl.screen.findByText("✓ Username válido")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Enviar" }));
    await rtl.waitFor(() =>
      expect(m.solicitar).toHaveBeenCalledWith({ marca_id: "m1", handle: "novo.perfil" }),
    );
  });

  it("shows the account select only when the org has more than one", async () => {
    m.contas.mockReturnValue({
      data: [
        { id: "c1", nome: "A", ig_username: "a" },
        { id: "c2", nome: "B", ig_username: "b" },
      ],
    });
    renderPage();
    await abrirSolicitar();
    expect(rtl.screen.getByLabelText("Conta usada para monitorar")).toBeTruthy();
  });
});
