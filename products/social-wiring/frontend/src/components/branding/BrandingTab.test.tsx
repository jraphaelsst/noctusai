/**
 * Branding tab — four states, grouping by marca, sandboxed previews, and the
 * rename / catalog-removal of the media-creation page.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const overview = vi.fn();
const detail = vi.fn();
const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

vi.mock("@/hooks/useBranding", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useBranding")>("@/hooks/useBranding");
  return {
    ...actual,
    useBrandingOverview: () => overview(),
    useBrandingDetail: (id: string | null) => detail(id),
    useDeleteBranding: () => noopMutation,
    useCreateBranding: () => noopMutation,
    useImportDesignSystem: () => noopMutation,
    useUpdateBranding: () => noopMutation,
    useUpsertComponent: () => noopMutation,
    useDeleteComponent: () => noopMutation,
    useUploadAsset: () => noopMutation,
    useAddLinkReference: () => noopMutation,
    useDeleteReference: () => noopMutation,
  };
});
vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Nós no Limiar" }], isPending: false }),
}));

const SUMMARY = {
  id: "k1",
  name: "Nós no Limiar",
  slug: "nos-no-limiar",
  marca_id: "m1",
  is_template: false,
  default_lang: "pt-BR",
  created_at: "",
  updated_at: "",
};

const TOKENS = {
  name: "NNL",
  color: {
    themes: [
      { id: "light", name: "Light" },
      { id: "dark", name: "Dark" },
    ],
    tokens: [
      { name: "wine", value: "#6b1f2a", usage: "Primary action" },
      { name: "surface", value: { light: "{wine}", dark: "#000000" }, usage: "bg" },
    ],
  },
  type: {
    fonts: [],
    families: { ui: "Inter, sans-serif" },
    groups: [
      {
        name: "UI",
        family: "ui",
        styles: [{ name: "body", fontSize: "16px", lineHeight: "24px", fontWeight: 400, sample: "Olá", usage: "text" }],
      },
    ],
  },
  radius: { tokens: [{ name: "radius-pill", value: "999px", usage: "pills" }] },
};

const DETAIL = {
  ...SUMMARY,
  persona: "",
  design_system: "",
  tokens: TOKENS,
  brand_book: "# Livro\n\nTexto do brand book",
  sections: [{ title: "Voz", markdown: "Direta" }],
  marca: { id: "m1", name: "Nós no Limiar", slug: "nos-no-limiar", kind: "empresa" },
  components: [
    {
      id: "c1",
      brand_kit_id: "k1",
      name: "Chip",
      guideline_md: "Guideline do chip",
      preview_html: "<script>alert(1)</script><div id='x'>chip</div>",
      position: 0,
    },
  ],
  assets: [
    {
      id: "a1",
      brand_kit_id: "k1",
      kind: "logo",
      label: "logo.png",
      asset_url: null,
      notes: null,
      storage_path: "o/b/logo",
      content_type: "image/png",
      size_bytes: 2048,
      signed_url: "https://signed.example/logo.png",
      signed_url_error: null,
    },
  ],
};

async function renderTab() {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const { BrandingTab } = await import("./BrandingTab");
  return rtl.render(React.createElement(BrandingTab));
}

beforeEach(() => {
  vi.clearAllMocks();
  detail.mockReturnValue({ data: undefined, error: null, showSkeleton: false, isRefreshing: false });
});

describe("BrandingTab list states", () => {
  it("skeleton while pending with no data", async () => {
    overview.mockReturnValue({ data: undefined, error: null, showSkeleton: true, isRefreshing: false });
    const { getByTestId, queryByTestId } = await renderTab();
    expect(getByTestId("branding-list-loading")).toBeTruthy();
    expect(queryByTestId("branding-row-k1")).toBeNull();
  });

  it("error state distinct from empty", async () => {
    overview.mockReturnValue({ data: undefined, error: new Error("boom"), showSkeleton: false, isRefreshing: false });
    const { getByText, queryByText } = await renderTab();
    expect(getByText(/não foi possível carregar os brandings/i)).toBeTruthy();
    expect(queryByText(/nenhuma marca ou branding/i)).toBeNull();
  });

  it("empty state", async () => {
    overview.mockReturnValue({
      data: { template: null, marcas: [], unassigned: [] },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    const { getByText } = await renderTab();
    expect(getByText(/nenhuma marca ou branding ainda/i)).toBeTruthy();
  });

  it("groups brandings by marca, template on top, no catalog button", async () => {
    overview.mockReturnValue({
      data: {
        template: { ...SUMMARY, id: "kt", name: "Branding Template", marca_id: null, is_template: true },
        marcas: [
          { id: "m1", name: "Nós no Limiar", slug: "nnl", kind: "empresa", brandings: [SUMMARY] },
          { id: "m2", name: "NoctusAI", slug: "n", kind: "empresa", brandings: [] },
        ],
        unassigned: [],
      },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    const { getByTestId, queryByText, getByText } = await renderTab();
    expect(getByTestId("branding-group-template").textContent).toContain("Branding Template");
    expect(getByTestId("branding-group-m1").textContent).toContain("Nós no Limiar");
    expect(getByTestId("branding-group-m2").textContent).toContain("Nenhum branding");
    expect(getByText("Importar design system")).toBeTruthy();
    expect(queryByText(/carregar catálogo/i)).toBeNull();
  });
});

describe("BrandingView", () => {
  async function openView() {
    overview.mockReturnValue({
      data: { template: null, marcas: [{ id: "m1", name: "Nós no Limiar", slug: "n", kind: "empresa", brandings: [SUMMARY] }], unassigned: [] },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    detail.mockReturnValue({ data: DETAIL, error: null, showSkeleton: false, isRefreshing: false });
    const view = await renderTab();
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(view.getByTestId("branding-row-k1"));
    return { view, rtl };
  }

  it("shows colour tokens per theme with swatches and usage", async () => {
    const { view, rtl } = await openView();
    expect(view.getByTestId("branding-color-wine").textContent).toContain("Primary action");
    expect(view.getByTestId("branding-color-surface").textContent).toContain("#6b1f2a");
    rtl.fireEvent.click(view.getByTestId("branding-theme-dark"));
    expect(view.getByTestId("branding-color-surface").textContent).toContain("#000000");
  });

  it("shows the skeleton and error states of the detail", async () => {
    overview.mockReturnValue({
      data: { template: null, marcas: [{ id: "m1", name: "N", slug: "n", kind: null, brandings: [SUMMARY] }], unassigned: [] },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    detail.mockReturnValue({ data: undefined, error: null, showSkeleton: true, isRefreshing: false });
    const v1 = await renderTab();
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(v1.getByTestId("branding-row-k1"));
    expect(v1.getByTestId("branding-view-loading")).toBeTruthy();
    v1.unmount();
    detail.mockReturnValue({ data: undefined, error: new Error("x"), showSkeleton: false, isRefreshing: false });
    const v2 = await renderTab();
    rtl.fireEvent.click(v2.getByTestId("branding-row-k1"));
    expect(v2.getByText(/não foi possível carregar o branding/i)).toBeTruthy();
  });

  it("renders type styles, the brand book and sections", async () => {
    const { view } = await openView();
    const user = (await import("@testing-library/user-event")).default.setup();
    await user.click(view.getByRole("tab", { name: "Tipografia" }));
    expect(view.getByTestId("branding-type-body")).toBeTruthy();
    await user.click(view.getByRole("tab", { name: "Espaçamento e raios" }));
    expect(view.getByTestId("branding-scales").textContent).toContain("radius-pill");
    await user.click(view.getByRole("tab", { name: "Brand book" }));
    expect(view.getByTestId("branding-book").textContent).toContain("Texto do brand book");
    expect(view.getByTestId("branding-book").textContent).toContain("Direta");
  });

  it("renders component previews ONLY in a script-less sandboxed iframe", async () => {
    const { view } = await openView();
    const user = (await import("@testing-library/user-event")).default.setup();
    await user.click(view.getByRole("tab", { name: /Componentes/ }));
    const frame = view.getByTestId("branding-preview-Chip") as HTMLIFrameElement;
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("Content-Security-Policy");
    expect(frame.getAttribute("srcdoc")).toContain("--wine:#6b1f2a");
    // never injected into the page DOM
    expect(document.querySelector("#x")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(view.getByText("Guideline do chip")).toBeTruthy();
  });

  it("lists assets with signed image urls", async () => {
    const { view } = await openView();
    const user = (await import("@testing-library/user-event")).default.setup();
    await user.click(view.getByRole("tab", { name: /Ativos/ }));
    const img = view.getByAltText("logo.png") as HTMLImageElement;
    expect(img.src).toBe("https://signed.example/logo.png");
  });

  it("offers create-from-template on the template only", async () => {
    overview.mockReturnValue({
      data: { template: { ...SUMMARY, id: "kt", is_template: true, marca_id: null }, marcas: [], unassigned: [] },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    detail.mockReturnValue({ data: { ...DETAIL, id: "kt", is_template: true, marca_id: null, marca: null }, error: null, showSkeleton: false, isRefreshing: false });
    const view = await renderTab();
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(view.getByTestId("branding-row-kt"));
    expect(view.getByTestId("branding-create-from-template")).toBeTruthy();
    expect(view.queryByTestId("branding-delete")).toBeNull();
  });
});

describe("MediaCreation page", () => {
  it("renames the tab to Branding and drops the catalog loader", async () => {
    overview.mockReturnValue({ data: { template: null, marcas: [], unassigned: [] }, error: null, showSkeleton: false, isRefreshing: false });
    vi.doMock("@/hooks/useMediaCreation", () => ({
      useBrandKits: () => ({ items: [], loading: false, error: null, refresh: vi.fn() }),
      usePosts: () => ({ items: [], loading: false, error: null, refresh: vi.fn() }),
      usePost: () => ({ post: null, loading: false, refresh: vi.fn() }),
      usePostGeneration: () => ({}),
    }));
    const React = (await import("react")).default;
    const rtl = await import("@testing-library/react");
    const { default: MediaCreation } = await import("@/pages/MediaCreation");
    const view = rtl.render(React.createElement(MediaCreation));
    expect(view.getByRole("tab", { name: "Biblioteca" })).toBeTruthy();
    expect(view.getByRole("tab", { name: "Novo post" })).toBeTruthy();
    expect(view.getByRole("tab", { name: "Branding" })).toBeTruthy();
    expect(view.queryByText(/Kits de marca/)).toBeNull();
    expect(view.queryByText(/Carregar catálogo/)).toBeNull();
    vi.doUnmock("@/hooks/useMediaCreation");
  });
});
