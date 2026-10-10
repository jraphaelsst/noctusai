/** FE-3: "No post" badge + "Criar post" action (esteira-contract.md §3.4/§6.3), real hooks over a mocked api. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ApiError } from "@noctusai/lib";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { CriarPostButton, NoPostBadge } from "./PostEsteira";

afterEach(() => {
  cleanup();
  Object.values(api).forEach((m) => m.mockReset());
  toast.success.mockReset();
  toast.error.mockReset();
});

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function renderUi(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/media-creation/headlines/favoritas"]}>
        <Routes>
          <Route path="*" element={<>{ui}<Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NoPostBadge", () => {
  it("mostra título e etapa e leva à Esteira com o post aberto", () => {
    renderUi(<NoPostBadge post={{ id: "p1", titulo: "Reel do ap", etapa_label: "Roteiro" }} />);
    const link = screen.getByTestId("no-post-badge");
    expect(link).toHaveTextContent("No post: Reel do ap · Roteiro");
    expect(link).toHaveAttribute("href", "/media-creation/esteira?post=p1");
  });

  it("não renderiza nada sem post", () => {
    renderUi(<NoPostBadge post={null} />);
    expect(screen.queryByTestId("no-post-badge")).toBeNull();
  });
});

describe("CriarPostButton", () => {
  it("cria o post com marca + headline e abre a Esteira nele", async () => {
    api.post.mockResolvedValue({ data: { id: "p9" } });
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/media-creation/esteira?post=p9"));
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts", { marca_id: "m1", headline_id: "h1" });
    expect(toast.success).toHaveBeenCalled();
  });

  it("do roteiro: cria o post e vincula o roteiro", async () => {
    api.post.mockResolvedValue({ data: { id: "p9" } });
    api.put.mockResolvedValue({ data: { id: "p9" } });
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" roteiroId="r1" titulo="Roteiro X" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("post=p9"));
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts", {
      marca_id: "m1",
      headline_id: "h1",
      titulo: "Roteiro X",
    });
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p9/roteiro", { roteiro_id: "r1" });
  });

  it("409 headline_ja_em_post: avisa, oferece 'Abrir post' com o post_id do servidor, não navega sozinho", async () => {
    api.post.mockRejectedValue(
      new ApiError(409, "headline_ja_em_post", { detail: { code: "headline_ja_em_post", post_id: "p7" } }),
    );
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const [msg, opts] = toast.error.mock.calls[0];
    expect(msg).toBe("Esta headline já está em um post.");
    expect(opts.action.label).toBe("Abrir post");
    expect(screen.getByTestId("where")).toHaveTextContent("/media-creation/headlines/favoritas");
    expect(screen.getByRole("button", { name: /criar post/i })).toBeEnabled();
    act(() => opts.action.onClick());
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/media-creation/esteira?post=p7"));
  });

  it("409 com envelope {error:{code,details:{post_id}}} também oferece 'Abrir post'", async () => {
    api.post.mockRejectedValue(
      new ApiError(409, "x", { error: { code: "headline_ja_em_post", details: { post_id: "p8" } } }),
    );
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error.mock.calls[0][1].action.label).toBe("Abrir post");
  });

  it("um 409 de outro código não é tratado como headline_ja_em_post", async () => {
    api.post.mockRejectedValue(new ApiError(409, "conflito qualquer", { detail: { code: "outro" } }));
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("conflito qualquer"));
  });

  it("erro genérico: mostra a mensagem do servidor", async () => {
    api.post.mockRejectedValue(new Error("[500] falhou geral"));
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("falhou geral"));
  });

  it("desabilita durante a criação (sem esconder o botão)", async () => {
    let resolver: (v: unknown) => void = () => {};
    api.post.mockReturnValue(new Promise((r) => (resolver = r)));
    renderUi(<CriarPostButton marcaId="m1" headlineId="h1" />);
    fireEvent.click(screen.getByRole("button", { name: /criar post/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /criando/i })).toBeDisabled());
    resolver({ data: { id: "p2" } });
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("post=p2"));
  });

  it("some quando a linha já está num post, e fica desabilitado sem marca", () => {
    const { unmount } = renderUi(
      <CriarPostButton marcaId="m1" headlineId="h1" post={{ id: "p1", titulo: "T", etapa_label: "E" }} />,
    );
    expect(screen.queryByRole("button", { name: /criar post/i })).toBeNull();
    unmount();
    renderUi(<CriarPostButton marcaId={null} headlineId="h1" />);
    expect(screen.getByRole("button", { name: /criar post/i })).toBeDisabled();
  });
});
