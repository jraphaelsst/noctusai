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
  pagina: vi.fn(),
  refs: vi.fn(),
  verificar: vi.fn(),
  contas: vi.fn(),
  solicitar: vi.fn(),
  removerRef: vi.fn(),
  sincronizar: vi.fn(),
  criar: vi.fn(),
  admin: vi.fn(),
  optouts: vi.fn(),
  registrarOptout: vi.fn(),
  removerOptout: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  PERFIS_POR_PAGINA: 30,
  usePerfisMonitorados: () => m.perfis(),
  usePerfisBiblioteca: () => m.pagina(),
  useReferencias: () => m.refs(),
  useVerificarPerfil: (h: string) => m.verificar(h),
  useContasDescoberta: () => m.contas(),
  useSolicitarPerfil: () => ({ mutateAsync: m.solicitar, isPending: false }),
  useCriarReferencias: () => ({ mutateAsync: m.criar, isPending: false }),
  useSincronizarPerfil: () => ({ mutateAsync: m.sincronizar, isPending: false }),
  useAtualizarPerfil: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverPerfil: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverReferencia: () => ({ mutateAsync: m.removerRef, isPending: false }),
  useOptoutsAdmin: () => m.optouts(),
  useRegistrarOptout: () => ({ mutateAsync: m.registrarOptout, isPending: false }),
  useRemoverOptout: () => ({ mutateAsync: m.removerOptout, isPending: false }),
}));
vi.mock("@/hooks/geracao/useTreinamentos", () => ({
  useTreinamentosAdmin: () => m.admin(),
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
  optout_contato: "joaoraphaelsst@gmail.com",
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
  m.pagina.mockReturnValue(ok({ items: [perfil()], total: 1 }));
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
  m.admin.mockReturnValue({ data: false });
  m.optouts.mockReturnValue(ok([]));
  m.registrarOptout.mockResolvedValue({
    optout: { id: "o9" },
    criado: true,
    purgados: { perfis: 2, virais: 17, blobs_falhos: 0 },
  });
  m.removerOptout.mockResolvedValue(undefined);
});

describe("Minha Biblioteca", () => {
  it("says monitoring is not activated when ingestion is off", () => {
    m.admin.mockReturnValue({ data: true });
    renderPage();
    expect(rtl.screen.getByText(/Monitoramento ainda não ativado/)).toBeTruthy();
    expect(rtl.screen.getAllByText("Aguardando").length).toBeGreaterThan(0);
  });

  it("no banner once ingestion is active", () => {
    const ativo = perfil({ status: "ativo", ultima_sync_em: "2026-10-01T00:00:00Z", virais: 5, ingestao_ativa: true });
    m.perfis.mockReturnValue(ok([ativo]));
    m.pagina.mockReturnValue(ok({ items: [ativo], total: 1 }));
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

describe("Perfis da biblioteca (platform-wide, admin-only writes)", () => {
  it("a member's profile has no status/monitorar/ultima_sync_em keys: no status badge, no stale-date column", () => {
    const { status: _s, erro_mensagem: _e, ultima_sync_em: _u, ...semAdmin } = perfil();
    m.pagina.mockReturnValue(ok({ items: [semAdmin], total: 1 }));
    renderPage();
    const tabela = rtl.screen.getByText("Perfis da biblioteca", { selector: "h2" }).closest("section")!;
    expect(rtl.within(tabela).getByText("@fulano")).toBeTruthy();
    expect(rtl.within(tabela).queryByText("Aguardando")).toBeNull();
    expect(rtl.within(tabela).queryByText("Pausado")).toBeNull();
    expect(rtl.within(tabela).queryByRole("columnheader", { name: "Status" })).toBeNull();
    expect(rtl.within(tabela).queryByRole("columnheader", { name: "Última atualização" })).toBeNull();
  });

  it("a member sees the profiles but none of the write controls", () => {
    renderPage();
    const tabela = rtl.screen.getByText("Perfis da biblioteca", { selector: "h2" }).closest("section")!;
    expect(rtl.within(tabela).getByText("@fulano")).toBeTruthy();
    expect(rtl.within(tabela).queryByRole("button", { name: "Atualizar agora" })).toBeNull();
    expect(rtl.within(tabela).queryByRole("button", { name: "Pausar" })).toBeNull();
    expect(rtl.within(tabela).queryByRole("button", { name: "Remover" })).toBeNull();
  });

  it("an admin gets them", () => {
    m.admin.mockReturnValue({ data: true });
    renderPage();
    const tabela = rtl.screen.getByText("Perfis da biblioteca", { selector: "h2" }).closest("section")!;
    expect(rtl.within(tabela).getByRole("button", { name: "Atualizar agora" })).toBeTruthy();
    expect(rtl.within(tabela).getByRole("button", { name: "Remover" })).toBeTruthy();
  });

  it("pages the library: shows the range and total, Próxima is off on the last page", () => {
    m.pagina.mockReturnValue(ok({ items: [perfil()], total: 1 }));
    renderPage();
    expect(rtl.screen.getByTestId("perfis-pagina").textContent).toBe("1–1 de 1");
    expect((rtl.screen.getByRole("button", { name: "Próxima" }) as HTMLButtonElement).disabled).toBe(true);
    expect((rtl.screen.getByRole("button", { name: "Anterior" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a coded 403 on an admin-only write is said out loud", async () => {
    // A member who somehow triggers the write (stale is_admin) still gets the sentence, never silence.
    m.admin.mockReturnValue({ data: true });
    m.sincronizar.mockRejectedValue(Object.assign(new Error("[403] x"), { status: 403 }));
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Atualizar agora" }));
    const { toast } = await import("sonner");
    await rtl.waitFor(() => expect((toast.error as any).mock.calls.flat().join(" ")).toContain("Somente administradores"));
  });
});

describe("Solicitar Perfil (platform admin only)", () => {
  it("a member cannot add profiles: sees the notice, no form, no request", async () => {
    renderPage();
    await abrirSolicitar();
    expect(rtl.screen.getByTestId("perfil-somente-admin").textContent).toContain("somente administradores adicionam perfis");
    expect(rtl.screen.queryByLabelText(/Perfil do Instagram/)).toBeNull();
    expect(m.solicitar).not.toHaveBeenCalled();
  });
});

describe("Solicitar Perfil live check", () => {
  beforeEach(() => m.admin.mockReturnValue({ data: true }));

  it("rejects a post link without calling the check", async () => {
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "https://instagram.com/reel/abc/");
    expect(await rtl.screen.findByText(/não o link de um post/)).toBeTruthy();
    expect(m.verificar).not.toHaveBeenCalledWith("abc");
    expect((rtl.screen.getByRole("button", { name: "Adicionar perfil" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it.each([
    ["ja_monitorado", "⚠️ Este perfil já está na biblioteca (monitorado)"],
    ["na_minha_biblioteca", "⚠️ Este perfil já está na sua biblioteca."],
    ["sem_conta_descoberta", "✗ Nenhuma fonte de dados configurada para monitorar perfis. Fale com o administrador."],
  ])("status %s blocks submit with its message", async (status, texto) => {
    m.verificar.mockImplementation((h: string) => ({ data: h ? { status } : undefined, isFetching: false, isError: false }));
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@novo");
    expect(await rtl.screen.findByText(texto)).toBeTruthy();
    expect((rtl.screen.getByRole("button", { name: "Adicionar perfil" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("valid username enables Adicionar perfil and posts the normalized handle (no marca_id: the library is platform-wide)", async () => {
    m.verificar.mockImplementation((h: string) => ({
      data: h ? { status: "disponivel" } : undefined,
      isFetching: false,
      isError: false,
    }));
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@Novo.Perfil");
    expect(await rtl.screen.findByText("✓ Username válido")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Adicionar perfil" }));
    await rtl.waitFor(() =>
      expect(m.solicitar).toHaveBeenCalledWith({ handle: "novo.perfil" }),
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

describe("Opt-out (LGPD)", () => {
  const comoAdmin = () => m.admin.mockReturnValue({ data: true });
  it("names the opt-out e-mail in the transparency note (default when no profile yet)", async () => {
    comoAdmin();
    renderPage();
    await abrirSolicitar();
    const nota = rtl.screen.getByTestId("nota-transparencia").textContent ?? "";
    expect(nota).toContain("Somente perfis públicos de empresa/criador podem ser monitorados.");
    expect(nota).toContain("pelo e-mail joaoraphaelsst@gmail.com.");
  });

  it("uses the configurable contact served by the profiles list", async () => {
    m.perfis.mockReturnValue(ok([perfil({ optout_contato: "privacidade@exemplo.com" })]));
    comoAdmin();
    renderPage();
    await abrirSolicitar();
    const nota = rtl.screen.getByTestId("nota-transparencia").textContent ?? "";
    expect(nota).toContain("pelo e-mail privacidade@exemplo.com.");
  });

  it("perfil_optout on the live check is a clear inline message, not a generic error", async () => {
    m.verificar.mockImplementation((h: string) => ({
      data: undefined,
      isFetching: false,
      isError: !!h,
      error: h ? Object.assign(new Error("[422] x"), { code: "perfil_optout" }) : null,
    }));
    comoAdmin();
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@pediu");
    expect(await rtl.screen.findByText("Este perfil pediu para não ser monitorado.")).toBeTruthy();
    expect(rtl.screen.queryByText(/Não foi possível verificar/)).toBeNull();
  });

  it("the opt-out message clears as soon as the handle is cleared or edited", async () => {
    // Worst case: the query keeps handing back the stale opt-out error for the old handle.
    m.verificar.mockReturnValue({
      data: undefined,
      isFetching: false,
      isError: true,
      error: Object.assign(new Error("[422] x"), { code: "perfil_optout" }),
    });
    comoAdmin();
    renderPage();
    await abrirSolicitar();
    const campo = rtl.screen.getByLabelText(/Perfil do Instagram/);
    await userEvent.type(campo, "@pediu");
    expect(await rtl.screen.findByText("Este perfil pediu para não ser monitorado.")).toBeTruthy();
    await userEvent.type(campo, "x");
    expect(rtl.screen.queryByText("Este perfil pediu para não ser monitorado.")).toBeNull();
    await userEvent.clear(campo);
    expect(rtl.screen.queryByText("Este perfil pediu para não ser monitorado.")).toBeNull();
  });

  it("perfil_optout on submit shows the inline message", async () => {
    m.verificar.mockImplementation((h: string) => ({ data: h ? { status: "disponivel" } : undefined, isFetching: false, isError: false }));
    m.solicitar.mockRejectedValue(Object.assign(new Error("[422] x"), { code: "perfil_optout" }));
    comoAdmin();
    renderPage();
    await abrirSolicitar();
    await userEvent.type(rtl.screen.getByLabelText(/Perfil do Instagram/), "@pediu");
    await rtl.screen.findByText("✓ Username válido");
    await userEvent.click(rtl.screen.getByRole("button", { name: "Adicionar perfil" }));
    expect(await rtl.screen.findByText("Este perfil pediu para não ser monitorado.")).toBeTruthy();
  });

  it("hides the admin panel from non-admins", () => {
    renderPage();
    expect(rtl.screen.queryByText("Pedidos de exclusão (opt-out)")).toBeNull();
  });

  it("admin: lists, registers behind a confirm and reports the purge counts", async () => {
    m.admin.mockReturnValue({ data: true });
    m.optouts.mockReturnValue(
      ok([{ id: "o1", handle: "velho", motivo: "pediu", origem: "dpo", solicitado_em: null, registrado_por: null, created_at: "2026-10-01T00:00:00Z" }]),
    );
    renderPage();
    const painel = rtl.screen.getByTestId("optouts-admin");
    expect(rtl.within(painel).getByText("@velho")).toBeTruthy();
    await userEvent.type(rtl.within(painel).getByLabelText(/Perfil \(@handle/), "@novo");
    await userEvent.selectOptions(rtl.within(painel).getByLabelText("Origem"), "dpo");
    await userEvent.click(rtl.within(painel).getByRole("button", { name: "Registrar opt-out" }));
    expect(await rtl.screen.findByText(/apaga AGORA todos os dados deste perfil em todas as organizações/)).toBeTruthy();
    expect(m.registrarOptout).not.toHaveBeenCalled();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Apagar e registrar" }));
    await rtl.waitFor(() => expect(m.registrarOptout).toHaveBeenCalledWith({ handle: "@novo", origem: "dpo" }));
    const { toast } = await import("sonner");
    await rtl.waitFor(() => expect((toast.success as any).mock.calls.flat().join(" ")).toMatch(/2 perfil.*17 viral/));
  });

  it("admin: removing an opt-out needs the confirm", async () => {
    m.admin.mockReturnValue({ data: true });
    m.optouts.mockReturnValue(
      ok([{ id: "o1", handle: "velho", motivo: null, origem: "email", solicitado_em: null, registrado_por: null, created_at: "2026-10-01T00:00:00Z" }]),
    );
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Remover opt-out de @velho" }));
    expect(m.removerOptout).not.toHaveBeenCalled();
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Remover opt-out" }));
    await rtl.waitFor(() => expect(m.removerOptout).toHaveBeenCalledWith("o1"));
  });
});
