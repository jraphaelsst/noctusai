/**
 * Biblioteca page + ViralModal + wizard + VideoPicker. The geracao hooks are
 * mocked (BE is not built yet); tests pin the contract-visible behaviour.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Biblioteca from "./Biblioteca";
import { VideoPicker, default as VideoPickerDefault } from "@/components/geracao/biblioteca/VideoPicker";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({
  virais: vi.fn(),
  detalhe: vi.fn(),
  perfis: vi.fn(),
  tax: vi.fn(),
  criarRef: vi.fn(),
  gerar: vi.fn(),
  assuntos: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  VIRAIS_POR_PAGINA: 24,
  useViraisBiblioteca: (...a: any[]) => m.virais(...a),
  useViralDetalhe: (...a: any[]) => m.detalhe(...a),
  usePerfisMonitorados: () => m.perfis(),
  useCriarReferencias: () => ({ mutateAsync: m.criarRef, isPending: false }),
  useGerarHeadlineViral: () => ({ mutateAsync: m.gerar, isPending: false }),
}));
vi.mock("@/hooks/geracao/useTaxonomias", () => ({
  useTaxonomias: () => m.tax(),
}));
vi.mock("@/hooks/useAssuntosVirais", () => ({
  useAssuntosVirais: (...a: any[]) => m.assuntos(...a),
}));

const viral = (over: Partial<any> = {}) => ({
  id: "v1",
  codigo: 101,
  perfil: { id: "p1", handle: "fulano" },
  thumbnail_url: null,
  permalink: "https://www.instagram.com/reel/AbC123/",
  publicado_em: "2026-09-01T00:00:00Z",
  views: null,
  likes: 1500,
  comments: null,
  duracao_s: 65,
  score_viral: 4.2,
  e_viral: true,
  trecho: null,
  ...over,
});

const detalhe = (over: Partial<any> = {}) => ({
  ...viral(),
  caption: "legenda",
  gancho: "gancho",
  transcricao_texto: "texto da transcrição",
  transcricao_status: "concluida",
  classificacao_status: "concluida",
  nichos: [{ id: 1, nome: "Imóveis" }],
  profissoes: [],
  formatos: [],
  gatilho: "misterio",
  estrutura_utilizavel: true,
  ...over,
});

const pageState = (items: any[], over: Partial<any> = {}) => ({
  data: { items, total: items.length, page: 1, filtro_automatico: false },
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

function Loc() {
  const l = useLocation();
  return <div data-testid="loc">{l.pathname + l.search}</div>;
}

function renderPage(url = "/media-creation/biblioteca") {
  return rtl.render(
    <MemoryRouter initialEntries={[url]}>
      <Biblioteca />
      <Loc />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.virais.mockReturnValue(pageState([viral(), viral({ id: "v2", codigo: 102 })]));
  m.detalhe.mockReturnValue({ data: detalhe(), showSkeleton: false, isError: false, refetch: vi.fn() });
  m.perfis.mockReturnValue({
    data: [{ id: "p1", handle: "fulano", ultima_sync_em: "2026-10-01T00:00:00Z", virais: 3 }],
    showSkeleton: false,
    isError: false,
  });
  m.tax.mockReturnValue({ data: { nichos: [], profissoes: [], formatos: [], gatilhos: [], tons: [] } });
  m.assuntos.mockReturnValue({
    items: [{ id: "a1", topic: "reforma de banheiro" }, { id: "a2", topic: "financiamento" }],
    showSkeleton: false,
    isError: false,
    refetch: vi.fn(),
  });
  m.criarRef.mockResolvedValue({ criadas: 2, ja_existentes: 0 });
  m.gerar.mockResolvedValue({ id: "l1" });
});

describe("Biblioteca page", () => {
  it("shows '—' for missing metrics, never 0", () => {
    renderPage();
    const card = rtl.screen.getByTestId("viral-card-v1");
    expect(card.textContent).toContain("1,5K");
    expect(card.textContent).toContain("👁 —");
    expect(card.textContent).toContain("💬 —");
    expect(card.textContent).toContain("1:05");
  });

  it("shows the auto-filter banner only when the server applied it and no profile is set", () => {
    m.virais.mockReturnValue(
      pageState([viral()], { data: { items: [viral()], total: 1, page: 1, filtro_automatico: true } }),
    );
    renderPage();
    expect(rtl.screen.getByText("Filtros aplicados automaticamente")).toBeTruthy();
    rtl.cleanup();
    renderPage("/media-creation/biblioteca?perfil=p1");
    expect(rtl.screen.queryByText("Filtros aplicados automaticamente")).toBeNull();
  });

  it("passes URL filters to the query hook", () => {
    renderPage("/media-creation/biblioteca?ordem=mais_recentes&views_min=100000&page=2");
    const [marca, filtros] = m.virais.mock.calls[0];
    expect(marca).toBe("m1");
    expect(filtros.ordem).toBe("mais_recentes");
    expect(filtros.viewsMin).toBe(100000);
    expect(filtros.page).toBe(2);
  });

  it("empty state with no monitored profiles points to Solicitar Perfil", () => {
    m.virais.mockReturnValue(pageState([]));
    m.perfis.mockReturnValue({ data: [], showSkeleton: false, isError: false });
    renderPage();
    expect(rtl.screen.getByText(/Sua biblioteca ainda está vazia/)).toBeTruthy();
  });

  it("empty state with never-synced profiles says monitoring is not active", () => {
    m.virais.mockReturnValue(pageState([]));
    m.perfis.mockReturnValue({
      data: [{ id: "p1", handle: "fulano", ultima_sync_em: null, virais: 0 }],
      showSkeleton: false,
      isError: false,
    });
    renderPage();
    expect(rtl.screen.getByText(/monitoração dos perfis ainda não está ativa/)).toBeTruthy();
  });

  it("error state offers Tentar novamente", async () => {
    const refetch = vi.fn();
    m.virais.mockReturnValue({ data: undefined, showSkeleton: false, isRefreshing: false, isError: true, refetch });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("selection bar adds the selected videos to Minha Biblioteca", async () => {
    renderPage();
    await userEvent.click(rtl.screen.getByLabelText("Selecionar vídeo 101"));
    await userEvent.click(rtl.screen.getByLabelText("Selecionar vídeo 102"));
    expect(rtl.screen.getByText("2 vídeo(s) selecionado(s)")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Adicionar à Minha Biblioteca" }));
    await rtl.waitFor(() =>
      expect(m.criarRef).toHaveBeenCalledWith({
        marca_id: "m1",
        modo: "video",
        viral_ids: ["v1", "v2"],
      }),
    );
  });

  it("?viral= opens the modal with embed, transcript and badges; closing strips the param", async () => {
    renderPage("/media-creation/biblioteca?viral=v1");
    expect(await rtl.screen.findByText("Informações do Viral")).toBeTruthy();
    const iframe = document.querySelector("iframe");
    expect(iframe?.getAttribute("src")).toBe("https://www.instagram.com/p/AbC123/embed/");
    expect((rtl.screen.getByDisplayValue("texto da transcrição") as HTMLTextAreaElement).readOnly).toBe(true);
    expect(rtl.screen.getByText("Imóveis")).toBeTruthy();
    await userEvent.keyboard("{Escape}");
    await rtl.waitFor(() => expect(rtl.screen.getByTestId("loc").textContent).not.toContain("viral="));
  });

  it("does not render an iframe for a non-Instagram permalink", async () => {
    m.detalhe.mockReturnValue({
      data: detalhe({ permalink: "https://evil.com/p/abc/" }),
      showSkeleton: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage("/media-creation/biblioteca?viral=v1");
    await rtl.screen.findByText("Informações do Viral");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("a non-concluida transcription shows an honest status chip", async () => {
    m.detalhe.mockReturnValue({
      data: detalhe({ transcricao_texto: null, transcricao_status: "sem_orcamento" }),
      showSkeleton: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage("/media-creation/biblioteca?viral=v1");
    expect(await rtl.screen.findByText(/Transcrição adiada/)).toBeTruthy();
  });

  it("Gerar headline is disabled when the structure is unusable", async () => {
    m.detalhe.mockReturnValue({
      data: detalhe({ estrutura_utilizavel: false }),
      showSkeleton: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage("/media-creation/biblioteca?viral=v1");
    const btn = (await rtl.screen.findByRole("button", { name: "Gerar headline" })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("wizard runs 3 steps and posts origem biblioteca", async () => {
    renderPage("/media-creation/biblioteca?viral=v1");
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Gerar headline" }));
    expect(await rtl.screen.findByText("Escolha os assuntos virais")).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("reforma de banheiro"));
    await userEvent.type(
      rtl.screen.getByLabelText(/Escreva o assunto viral manualmente/),
      "meu assunto",
    );
    await userEvent.click(rtl.screen.getByRole("button", { name: /Próximo: Revisar e Enviar/ }));
    expect(rtl.screen.getByText("Revisar e Enviar")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Criar Headline" }));
    await rtl.waitFor(() =>
      expect(m.gerar).toHaveBeenCalledWith({
        marca_id: "m1",
        viral_id: "v1",
        assunto_ids: ["a1"],
        assunto_livre: "meu assunto",
      }),
    );
    expect(await rtl.screen.findByText("Headline enviada para criação!")).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: "Ver Headlines Sugeridas" })).toBeTruthy();
  });

  it("Citar no Chat links carry the viral / perfil ids", async () => {
    renderPage("/media-creation/biblioteca?viral=v1");
    const a = await rtl.screen.findByRole("link", { name: "Citar no Chat" });
    expect(a.getAttribute("href")).toBe("/media-creation/chat?cite_viral=v1");
    expect(
      rtl.screen.getByRole("link", { name: "Citar perfil no Chat" }).getAttribute("href"),
    ).toBe("/media-creation/chat?cite_perfil=p1");
  });
});

describe("VideoPicker (FE-3 contract)", () => {
  it("exports named + default and reports selection / removal through onChange", async () => {
    expect(VideoPickerDefault).toBe(VideoPicker);
    const onChange = vi.fn();
    const { rerender } = rtl.render(
      <MemoryRouter>
        <VideoPicker marcaId="m1" value={null} onChange={onChange} />
      </MemoryRouter>,
    );
    await userEvent.click(rtl.screen.getByRole("button", { name: "Abrir biblioteca e escolher vídeo" }));
    await userEvent.click(await rtl.screen.findByLabelText("Abrir viral 101 de @fulano"));
    expect(onChange).toHaveBeenCalledWith("v1");

    rerender(
      <MemoryRouter>
        <VideoPicker marcaId="m1" value="v1" onChange={onChange} />
      </MemoryRouter>,
    );
    expect(rtl.screen.getByTestId("video-escolhido").textContent).toContain("@fulano");
    await userEvent.click(rtl.screen.getByRole("button", { name: "remover" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("filters the picker query", async () => {
    rtl.render(
      <MemoryRouter>
        <VideoPicker marcaId="m1" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await userEvent.click(rtl.screen.getByRole("button", { name: "Abrir biblioteca e escolher vídeo" }));
    await userEvent.selectOptions(await rtl.screen.findByLabelText("Views mínimas"), "1000000");
    const last = m.virais.mock.calls[m.virais.mock.calls.length - 1];
    expect(last[1].viewsMin).toBe(1_000_000);
    expect(last[1].verTodos).toBe(true);
  });
});
