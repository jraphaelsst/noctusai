/** Back office — products list states + create → edit (offers) → delete, through the organ endpoints. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => ({ user: null }) }));

import { ApiError } from "@noctusai/lib";
import Products from "../admin/Products";
import ProductEdit from "../admin/ProductEdit";
import { renderRoutes } from "@/test-utils";

const PRODUCT = {
  id: "p1",
  slug: "curso-de-foto",
  title: "Curso de Foto",
  description: "",
  product_type: "digital",
  fulfillment_type: "digital_delivery",
  status: "draft",
  category_id: null,
  attributes: {},
  tax_treatment_override: null,
  created_at: "2026-10-12T10:00:00Z",
  updated_at: "2026-10-12T10:00:00Z",
  offers: [],
  media: [],
};

const page = (rows: unknown[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length, total_pages: 1 } });

function routeGets(products: unknown) {
  apiMock.get.mockImplementation((url: string) => {
    if (url === "/api/commerce/profile") return Promise.resolve({ data: null });
    if (url === "/api/commerce/categories") return Promise.resolve({ data: [] });
    if (url === "/api/commerce/products") return products instanceof Error ? Promise.reject(products) : Promise.resolve(products);
    if (url === "/api/commerce/products/p1") return Promise.resolve({ data: PRODUCT });
    if (url === "/api/commerce/products/p1/offers") return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

const ROUTES = {
  "/admin/produtos": <Products />,
  "/admin/produtos/:id": <ProductEdit />,
};

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Admin › Produtos", () => {
  it("lists real rows from GET /api/commerce/products and opens the editor on click", async () => {
    routeGets(page([PRODUCT]));
    renderRoutes("/admin/produtos", ROUTES);
    expect(await screen.findByText("Curso de Foto")).toBeInTheDocument();
    expect(screen.getByText("/curso-de-foto")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Curso de Foto"));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/admin/produtos/p1"));
  });

  it("shows the empty state when the store has no products", async () => {
    routeGets(page([]));
    renderRoutes("/admin/produtos", ROUTES);
    expect(await screen.findByText("Nenhum produto cadastrado ainda.")).toBeInTheDocument();
  });

  it("shows the error state with retry when the list fails", async () => {
    routeGets(new ApiError(500, "boom"));
    renderRoutes("/admin/produtos", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    routeGets(page([PRODUCT]));
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Curso de Foto")).toBeInTheDocument();
  });

  it("creates a product (POST) and lands on its own editor with the offers section", async () => {
    routeGets(page([]));
    apiMock.post.mockResolvedValue({ data: PRODUCT });
    renderRoutes("/admin/produtos", ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Novo produto" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/admin/produtos/novo"));
    expect(screen.getByText("Salve o produto para cadastrar ofertas e mídias.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Título/), { target: { value: "Curso de Foto" } });
    expect(screen.getByLabelText(/Slug/)).toHaveValue("curso-de-foto");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(1));
    const [url, body] = apiMock.post.mock.calls[0];
    expect(url).toBe("/api/commerce/products");
    expect(body).toMatchObject({ title: "Curso de Foto", slug: "curso-de-foto", product_type: "digital" });
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/admin/produtos/p1"));
    // Exactly one offers section: the one `ProductEditor` embeds (the page must not add a second).
    expect(await screen.findByRole("button", { name: "Nova oferta" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Nova oferta" })).toHaveLength(1));
  });

  it("surfaces a slug_em_uso create error instead of navigating", async () => {
    routeGets(page([]));
    apiMock.post.mockRejectedValue(
      new ApiError(409, "Slug em uso.", { error: { code: "slug_em_uso", message: "Slug em uso." } }),
    );
    renderRoutes("/admin/produtos/novo", ROUTES);
    fireEvent.change(await screen.findByLabelText(/Título/), { target: { value: "Curso" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled());
    expect(await screen.findByText(/Slug em uso/)).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/admin/produtos/novo");
  });

  it("updates (PATCH) and deletes (DELETE) an existing product, then returns to the list", async () => {
    routeGets(page([PRODUCT]));
    apiMock.patch.mockResolvedValue({ data: { ...PRODUCT, title: "Curso de Foto II" } });
    apiMock.delete.mockResolvedValue(undefined);
    renderRoutes("/admin/produtos/p1", ROUTES);

    const title = await screen.findByLabelText(/Título/);
    await waitFor(() => expect(title).toHaveValue("Curso de Foto"));
    fireEvent.change(title, { target: { value: "Curso de Foto II" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(apiMock.patch).toHaveBeenCalled());
    expect(apiMock.patch.mock.calls[0][0]).toBe("/api/commerce/products/p1");
    expect(apiMock.patch.mock.calls[0][1]).toMatchObject({ title: "Curso de Foto II" });

    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    const confirm = await screen.findAllByRole("button", { name: "Excluir" });
    fireEvent.click(confirm[confirm.length - 1]);
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith("/api/commerce/products/p1"));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/admin\/produtos$/));
  });
});
