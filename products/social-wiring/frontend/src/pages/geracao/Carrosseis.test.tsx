/**
 * Carrosséis page (ex-"Criação de mídia" Biblioteca + Novo post) and Branding
 * page: four states each, kit dropdown link, no unmount on refetch.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Carrosseis from "./Carrosseis";
import Branding from "./Branding";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({
  posts: vi.fn(),
  post: vi.fn(),
  kits: vi.fn(),
  overview: vi.fn(),
}));

vi.mock("@/hooks/useMediaCreation", () => ({
  usePosts: () => m.posts(),
  usePost: (id: string | null) => m.post(id),
  useBrandKits: () => m.kits(),
  usePostGeneration: () => ({ run: vi.fn(), render: vi.fn(), score: vi.fn(), pending: null }),
}));
vi.mock("@/hooks/useBranding", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useBranding")>("@/hooks/useBranding");
  const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
  return {
    ...actual,
    useBrandingOverview: () => m.overview(),
    useBrandingDetail: () => ({ data: undefined, showSkeleton: false, isRefreshing: false }),
    useDeleteBranding: () => noop,
    useCreateBranding: () => noop,
    useImportDesignSystem: () => noop,
    useUpdateBranding: () => noop,
  };
});
vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => ({ data: [], isPending: false }) }));

const POST = {
  id: "p1",
  title: "Carrossel A",
  idea: "ideia A",
  status: "draft",
  format: "carousel",
  variant: "premium",
  slide_count: 5,
  brand_kit: { id: "k1", name: "Kit 1" },
  slides: [],
};
const list = (over = {}) => ({
  items: [],
  loading: false,
  error: null,
  refresh: vi.fn(),
  remove: vi.fn(),
  create: vi.fn(),
  ...over,
});

const page = (node: React.ReactNode) => <MemoryRouter>{node}</MemoryRouter>;
const renderCarrosseis = () => rtl.render(page(<Carrosseis />));

beforeEach(() => {
  m.posts.mockReturnValue(list());
  m.post.mockReturnValue({ post: null, loading: false, refresh: vi.fn() });
  m.kits.mockReturnValue({ items: [], loading: false, error: null, refresh: vi.fn() });
});

describe("Carrosséis", () => {
  it("shows title, both tabs and the empty state", () => {
    const v = renderCarrosseis();
    expect(v.getByText("Carrosséis e posts de imagem")).toBeTruthy();
    expect(v.getByRole("tab", { name: "Biblioteca" })).toBeTruthy();
    expect(v.getByRole("tab", { name: "Novo post" })).toBeTruthy();
    expect(v.queryByRole("tab", { name: "Branding" })).toBeNull();
    expect(v.getByTestId("carrosseis-list-empty")).toBeTruthy();
  });

  it("loading: skeleton while nothing loaded", () => {
    m.posts.mockReturnValue(list({ loading: true }));
    const v = renderCarrosseis();
    expect(v.getByTestId("carrosseis-list-loading")).toBeTruthy();
    expect(v.queryByTestId("carrosseis-list-empty")).toBeNull();
  });

  it("refetch over existing items keeps the list (no skeleton, no empty)", () => {
    m.posts.mockReturnValue(list({ loading: true, items: [POST] }));
    const v = renderCarrosseis();
    expect(v.queryByTestId("carrosseis-list-loading")).toBeNull();
    expect(v.getByText("Carrossel A")).toBeTruthy();
  });

  it("error: message with retry", async () => {
    const refresh = vi.fn();
    m.posts.mockReturnValue(list({ error: "boom", refresh }));
    const v = renderCarrosseis();
    expect(v.getByTestId("carrosseis-list-error")).toBeTruthy();
    await userEvent.click(v.getByRole("button", { name: "Tentar novamente" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("success: selecting a post renders the detail; refetch does not unmount it", async () => {
    m.posts.mockReturnValue(list({ items: [POST] }));
    m.post.mockReturnValue({ post: POST, loading: false, refresh: vi.fn() });
    const v = renderCarrosseis();
    await userEvent.click(v.getByText("Carrossel A"));
    expect(v.getByText("Pipeline de geração")).toBeTruthy();
    m.post.mockReturnValue({ post: POST, loading: true, refresh: vi.fn() });
    v.rerender(page(<Carrosseis />));
    expect(v.getByText("Pipeline de geração")).toBeTruthy();
    expect(v.queryByTestId("post-detail-loading")).toBeNull();
  });

  it("detail: skeleton while loading, error with retry when it failed", async () => {
    m.posts.mockReturnValue(list({ items: [POST] }));
    m.post.mockReturnValue({ post: null, loading: true, refresh: vi.fn() });
    const v = renderCarrosseis();
    await userEvent.click(v.getByText("Carrossel A"));
    expect(v.getByTestId("post-detail-loading")).toBeTruthy();
    m.post.mockReturnValue({ post: null, loading: false, refresh: vi.fn() });
    v.rerender(page(<Carrosseis />));
    expect(v.getByTestId("post-detail-error")).toBeTruthy();
  });

  it("Novo post: kit dropdown links to Branding; empty kits point there; error retries", async () => {
    const v = renderCarrosseis();
    await userEvent.click(v.getByRole("tab", { name: "Novo post" }));
    const link = v.getByTestId("compose-manage-branding");
    expect(link.getAttribute("href")).toBe("/media-creation/branding");
    expect(v.getByTestId("compose-kits-empty")).toBeTruthy();
    const refresh = vi.fn();
    m.kits.mockReturnValue({ items: [], loading: false, error: "x", refresh });
    v.rerender(page(<Carrosseis />));
    await userEvent.click(v.getByRole("button", { name: "Tentar novamente" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("Novo post: skeleton while kits load", async () => {
    m.kits.mockReturnValue({ items: [], loading: true, error: null, refresh: vi.fn() });
    const v = renderCarrosseis();
    await userEvent.click(v.getByRole("tab", { name: "Novo post" }));
    expect(v.getByTestId("compose-kits-loading")).toBeTruthy();
  });
});

describe("Branding page", () => {
  const state = (over = {}) => ({
    data: undefined,
    error: null,
    showSkeleton: false,
    isRefreshing: false,
    ...over,
  });
  const renderBranding = () => rtl.render(page(<Branding />));

  it("header + loading / error / empty / data", () => {
    m.overview.mockReturnValue(state({ showSkeleton: true }));
    let v = renderBranding();
    expect(v.getByText("Identidade visual por marca")).toBeTruthy();
    expect(v.getByTestId("branding-list-loading")).toBeTruthy();
    rtl.cleanup();

    m.overview.mockReturnValue(state({ error: new Error("x") }));
    v = renderBranding();
    expect(v.getByText(/Não foi possível carregar os brandings/)).toBeTruthy();
    rtl.cleanup();

    m.overview.mockReturnValue(state({ data: { template: null, marcas: [], unassigned: [] } }));
    v = renderBranding();
    expect(v.getByText(/Nenhuma marca ou branding/)).toBeTruthy();
    rtl.cleanup();

    const k = {
      id: "k1",
      name: "Kit 1",
      slug: "k",
      marca_id: "m1",
      is_template: false,
      default_lang: "pt-BR",
      created_at: "",
      updated_at: "",
    };
    m.overview.mockReturnValue(
      state({ data: { template: null, marcas: [{ id: "m1", name: "Marca", brandings: [k] }], unassigned: [] } }),
    );
    v = renderBranding();
    expect(v.getByTestId("branding-row-k1")).toBeTruthy();
  });
});
