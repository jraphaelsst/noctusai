/**
 * Breadcrumbs organ: derivation from the nav registry, detail-route crumbs,
 * unknown-route fallback, group-menu keyboard, narrow-width collapse.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { Home } from "lucide-react";

import { Breadcrumbs, BreadcrumbRegistryContext, type BreadcrumbRegistry } from "./Breadcrumbs";
import { buildBreadcrumbTrail } from "./breadcrumb-trail";
import type { NavGroup } from "./Sidebar";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const NAV: NavGroup[] = [
  {
    key: "admin",
    label: "Administração",
    icon: Home,
    items: [],
    groups: [
      {
        key: "comercial",
        label: "Comercial",
        icon: Home,
        items: [
          { name: "Produtos", href: "/admin/products", icon: Home },
          { name: "Planos", href: "/admin/plans", icon: Home },
        ],
      },
      {
        key: "clientes",
        label: "Clientes",
        icon: Home,
        items: [
          { name: "Usuários", href: "/admin/users", icon: Home },
          { name: "Clientes", href: "/clientes", icon: Home },
        ],
      },
    ],
  },
];

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderAt(path: string, registry: Partial<BreadcrumbRegistry> = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <BreadcrumbRegistryContext.Provider value={{ navGroups: NAV, ...registry }}>
        <Breadcrumbs />
        <Where />
      </BreadcrumbRegistryContext.Provider>
    </MemoryRouter>,
  );
}

describe("buildBreadcrumbTrail", () => {
  it("derives Group / Subgroup / Page from the nav registry", () => {
    const t = buildBreadcrumbTrail({ navGroups: NAV, pathname: "/admin/products" });
    expect(t.map((c) => c.label)).toEqual(["Administração", "Comercial", "Produtos"]);
    expect(t[2]).toMatchObject({ current: true });
    expect(t[2]!.href).toBeUndefined();
    expect(t[1]!.menu).toEqual([
      { kind: "item", label: "Produtos", href: "/admin/products" },
      { kind: "item", label: "Planos", href: "/admin/plans" },
    ]);
  });

  it("falls back to the nearest known ancestor, then to Início", () => {
    const trail = buildBreadcrumbTrail({ navGroups: NAV, pathname: "/admin/products/9f3/whatever" });
    expect(trail[trail.length - 1]?.label).toBe("Produtos");
    const none = buildBreadcrumbTrail({ navGroups: NAV, pathname: "/nada/aqui" });
    expect(none).toEqual([{ key: "root", label: "Início", current: true }]);
  });
});

describe("Breadcrumbs", () => {
  it("renders an accessible nav with aria-current on the last crumb and hidden separators", () => {
    renderAt("/admin/products");
    const nav = screen.getByRole("navigation", { name: "Você está em" });
    expect(within(nav).getByRole("list")).toBeInTheDocument();
    const current = within(nav).getByText("Produtos");
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.closest("a")).toBeNull();
    const seps = nav.querySelectorAll('li[aria-hidden="true"]');
    expect(seps).toHaveLength(2);
  });

  it("detail route: a route spec supplies the crumb, the page crumb becomes a link, no raw id", () => {
    renderAt("/clientes/42", {
      routeCrumbs: [{ path: "/clientes/:id", crumb: ({ params }) => (params.id === "42" ? "Maria Souza" : undefined) }],
    });
    const nav = screen.getByRole("navigation", { name: "Você está em" });
    expect(within(nav).getByRole("link", { name: "Clientes" })).toHaveAttribute("href", "/clientes");
    expect(within(nav).getByText("Maria Souza")).toHaveAttribute("aria-current", "page");
    expect(nav.textContent).not.toContain("42");
  });

  it("detail route with an unresolved crumb shows a generic word, never the id", () => {
    renderAt("/clientes/77", { routeCrumbs: [{ path: "/clientes/:id", crumb: () => undefined }] });
    const nav = screen.getByRole("navigation", { name: "Você está em" });
    expect(within(nav).getByText("Detalhes")).toHaveAttribute("aria-current", "page");
    expect(within(nav).queryByText(/77/)).toBeNull();
  });

  it("reads handle.crumb (string or function of loader data) from a data router", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "/clientes",
          children: [
            { index: true, element: null },
            {
              path: ":id",
              loader: () => ({ nome: "Ana Lima" }),
              handle: { crumb: ({ data }: { data?: { nome: string } }) => data?.nome },
              element: <Breadcrumbs />,
            },
          ],
        },
      ],
      { initialEntries: ["/clientes/5"] },
    );
    render(
      <BreadcrumbRegistryContext.Provider value={{ navGroups: NAV }}>
        <RouterProvider router={router} />
      </BreadcrumbRegistryContext.Provider>,
    );
    // the data router runs its loader before the first match renders
    const nav = await screen.findByRole("navigation", { name: "Você está em" });
    expect(within(nav).getByRole("link", { name: "Clientes" })).toBeInTheDocument();
    expect(within(nav).getByText("Ana Lima")).toHaveAttribute("aria-current", "page");
  });

  it("unknown route renders the fallback crumb, not an empty header", () => {
    renderAt("/nada/aqui");
    expect(screen.getByRole("navigation", { name: "Você está em" })).toHaveTextContent("Início");
  });

  it("renders nothing outside a router (a Header consumer with no router must not crash)", () => {
    const { container } = render(
      <BreadcrumbRegistryContext.Provider value={{ navGroups: NAV }}>
        <Breadcrumbs />
      </BreadcrumbRegistryContext.Provider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing outside a shell registry", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  describe("group menu", () => {
    it("opens as a real menu, moves with arrows, Esc returns focus to the button", async () => {
      const user = userEvent.setup();
      renderAt("/admin/products");
      const btn = screen.getByRole("button", { name: "Comercial" });
      expect(btn).toHaveAttribute("aria-haspopup", "menu");
      expect(btn).toHaveAttribute("aria-expanded", "false");

      await user.click(btn);
      expect(btn).toHaveAttribute("aria-expanded", "true");
      const menu = screen.getByRole("menu", { name: "Comercial" });
      const items = within(menu).getAllByRole("menuitem");
      expect(items.map((i) => i.textContent)).toEqual(["Produtos", "Planos"]);
      // opens on the current page
      expect(items[0]).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(items[1]).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(items[0]).toHaveFocus();
      await user.keyboard("{End}");
      expect(items[1]).toHaveFocus();

      await user.keyboard("{Escape}");
      expect(screen.queryByRole("menu")).toBeNull();
      expect(btn).toHaveFocus();
      expect(btn).toHaveAttribute("aria-expanded", "false");
    });

    it("ArrowDown on the button opens it, and picking a page navigates sideways", async () => {
      const user = userEvent.setup();
      renderAt("/admin/products");
      screen.getByRole("button", { name: "Comercial" }).focus();
      await user.keyboard("{ArrowDown}");
      await user.click(screen.getByRole("menuitem", { name: "Planos" }));
      expect(screen.getByTestId("where")).toHaveTextContent("/admin/plans");
      expect(screen.queryByRole("menu")).toBeNull();
    });
  });

  describe("narrow width", () => {
    it("collapses to … / Parent / Current; the ellipsis opens the full path", async () => {
      vi.stubGlobal("matchMedia", (q: string) => ({
        matches: true,
        media: q,
        addEventListener: () => {},
        removeEventListener: () => {},
      }));
      const user = userEvent.setup();
      renderAt("/admin/products");
      const nav = screen.getByRole("navigation", { name: "Você está em" });
      expect(within(nav).queryByRole("button", { name: "Administração" })).toBeNull();
      expect(within(nav).getByRole("button", { name: "Comercial" })).toBeInTheDocument();
      expect(within(nav).getByText("Produtos")).toHaveAttribute("aria-current", "page");

      await user.click(within(nav).getByRole("button", { name: "…" }));
      expect(screen.getByRole("menu", { name: "…" })).toHaveTextContent("Administração");
    });
  });
});
