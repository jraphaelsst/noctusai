/**
 * Treinamentos.test.tsx — empty video state, allow-listed embed only, lesson switching,
 * admin edit (PUT payload), four states. API hooks mocked; no network.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TreinamentosDefault, { Treinamentos, urlEmbedSegura } from "./Treinamentos";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = vi.hoisted(() => ({ lista: vi.fn(), admin: vi.fn(), atualizar: vi.fn() }));
vi.mock("@/hooks/geracao/useTreinamentos", () => ({
  useTreinamentos: () => m.lista(),
  useTreinamentosAdmin: () => m.admin(),
  useAtualizarTreinamento: () => ({ mutateAsync: m.atualizar, isPending: false }),
}));

const aula = (n: number, over: Record<string, unknown> = {}) => ({
  id: `t${n}`,
  ordem: n,
  titulo: `Aula ${n}`,
  descricao: `Descrição ${n}`,
  video_url: null,
  ativo: true,
  ...over,
});
const q = (data: unknown, over: Record<string, unknown> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m.lista.mockReturnValue(q([aula(1), aula(2, { video_url: "https://iframe.mediadelivery.net/embed/1/abc" })]));
  m.admin.mockReturnValue({ data: false });
  m.atualizar.mockResolvedValue({});
});

describe("urlEmbedSegura", () => {
  it("accepts only https on allow-listed hosts", () => {
    expect(urlEmbedSegura("https://player.vimeo.com/video/1")).toBe("https://player.vimeo.com/video/1");
    expect(urlEmbedSegura("http://player.vimeo.com/video/1")).toBeNull();
    expect(urlEmbedSegura("https://evil.example.com/x")).toBeNull();
    expect(urlEmbedSegura("https://player.vimeo.com.evil.com/x")).toBeNull();
    expect(urlEmbedSegura("javascript:alert(1)")).toBeNull();
    expect(urlEmbedSegura("não é url")).toBeNull();
    expect(urlEmbedSegura(null)).toBeNull();
  });
});

describe("Treinamentos", () => {
  it("exports the page as default and named", () => {
    expect(TreinamentosDefault).toBe(Treinamentos);
  });

  it("shows the honest empty video state for a lesson without URL, and the iframe once one is selected", async () => {
    const user = userEvent.setup();
    const { container } = rtl.render(<Treinamentos />);
    expect(rtl.screen.getByText("Primeiros passos: da Bio aos primeiros roteiros")).toBeTruthy();
    expect(rtl.screen.getByText("Vídeo em produção — em breve.")).toBeTruthy();
    expect(container.querySelector("iframe")).toBeNull();
    expect(rtl.screen.getByText("Descrição 1")).toBeTruthy();

    await user.click(rtl.screen.getByRole("button", { name: /Aula 2/ }));
    const iframe = container.querySelector("iframe");
    expect(iframe?.getAttribute("src")).toBe("https://iframe.mediadelivery.net/embed/1/abc");
    expect(rtl.screen.queryByText("Vídeo em produção — em breve.")).toBeNull();
  });

  it("never embeds a URL outside the allow-list", () => {
    m.lista.mockReturnValue(q([aula(1, { video_url: "https://evil.example.com/v" })]));
    const { container } = rtl.render(<Treinamentos />);
    expect(container.querySelector("iframe")).toBeNull();
    expect(rtl.screen.getByText("Vídeo em produção — em breve.")).toBeTruthy();
  });

  it("hides edit controls from non-admins and shows them to admins", () => {
    rtl.render(<Treinamentos />);
    expect(rtl.screen.queryByLabelText("Editar aula 1")).toBeNull();
    rtl.cleanup();
    m.admin.mockReturnValue({ data: true });
    rtl.render(<Treinamentos />);
    expect(rtl.screen.getByLabelText("Editar aula 1")).toBeTruthy();
  });

  it("lets an admin edit a lesson (PUT payload; empty URL becomes null)", async () => {
    m.admin.mockReturnValue({ data: true });
    const user = userEvent.setup();
    rtl.render(<Treinamentos />);
    await user.click(rtl.screen.getByLabelText("Editar aula 2"));
    const url = (await rtl.screen.findByLabelText("URL do vídeo")) as HTMLInputElement;
    expect(url.value).toBe("https://iframe.mediadelivery.net/embed/1/abc");
    await user.clear(rtl.screen.getByLabelText("Título"));
    await user.type(rtl.screen.getByLabelText("Título"), "Novo título");
    await user.clear(url);
    await user.click(rtl.screen.getByRole("button", { name: "Salvar" }));
    await rtl.waitFor(() =>
      expect(m.atualizar).toHaveBeenCalledWith({
        id: "t2",
        titulo: "Novo título",
        descricao: "Descrição 2",
        video_url: null,
        ativo: true,
      }),
    );
  });

  it("shows skeleton, error (retry), empty states and keeps lessons while refreshing", async () => {
    m.lista.mockReturnValue(q(undefined, { showSkeleton: true }));
    let r = rtl.render(<Treinamentos />);
    expect(rtl.screen.getByTestId("treinamentos-skeleton")).toBeTruthy();
    r.unmount();

    const refetch = vi.fn();
    m.lista.mockReturnValue(q(undefined, { isError: true, refetch }));
    r = rtl.render(<Treinamentos />);
    await userEvent.setup().click(rtl.screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
    r.unmount();

    m.lista.mockReturnValue(q([]));
    r = rtl.render(<Treinamentos />);
    expect(rtl.screen.getByText("Nenhum treinamento disponível.")).toBeTruthy();
    r.unmount();

    m.lista.mockReturnValue(q([aula(1)], { isRefreshing: true }));
    rtl.render(<Treinamentos />);
    expect(rtl.screen.getByText("Atualizando…")).toBeTruthy();
    expect(rtl.screen.getByRole("button", { name: /Aula 1/ })).toBeTruthy();
  });
});
