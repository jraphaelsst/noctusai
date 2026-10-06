/**
 * Nested Sidebar groups (2026-10-05): 4-level nesting, accordion per level,
 * closable headers, auto-open path, most-specific current leaf, aria-current,
 * backward-compat flat config, per-product storage key.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Home, Users, Zap } from "lucide-react";

import { Sidebar, sidebarStorageKey } from "./Sidebar";
import type { NavGroup } from "./Sidebar";

afterEach(cleanup);

function createMemoryStorage(): Storage {
  let store: Record<string, string> = {};
  return {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = String(v);
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      store = {};
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length;
    },
  } as Storage;
}

const icon = Home;
const item = (name: string, href: string) => ({ name, href, icon });

const TREE: NavGroup[] = [
  {
    key: "admin",
    label: "Administracao",
    icon: Users,
    items: [item("Admin Home", "/admin")],
    groups: [
      {
        key: "admin-visao",
        label: "Visao geral",
        icon,
        items: [item("Vendas", "/admin/vendas")],
        groups: [
          {
            key: "admin-visao-rel",
            label: "Relatorios",
            icon,
            items: [item("Mensal", "/admin/vendas/mensal")],
          },
        ],
      },
      { key: "admin-clientes", label: "Clientes", icon, items: [item("Usuarios", "/admin/usuarios")] },
    ],
  },
  {
    key: "site",
    label: "Website",
    icon,
    items: [item("Docs", "/docs")],
  },
];

function renderSidebar(path: string, navGroups: NavGroup[] = TREE, storageKey?: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar
        brandIcon={Zap}
        brandTitle="T"
        brandSubtitle="S"
        navGroups={navGroups}
        storageKey={storageKey}
      />
    </MemoryRouter>,
  );
}

const trigger = (name: string) => screen.getByRole("button", { name });
const expanded = (name: string) => trigger(name).getAttribute("aria-expanded");

beforeEach(() => {
  Object.defineProperty(window, "localStorage", {
    value: createMemoryStorage(),
    configurable: true,
    writable: true,
  });
});

describe("Sidebar nesting", () => {
  it("renders L1 > L2 > L3 groups and the L4 leaf by opening each level", () => {
    renderSidebar("/nowhere");
    fireEvent.click(trigger("Administracao"));
    fireEvent.click(trigger("Visao geral"));
    fireEvent.click(trigger("Relatorios"));
    expect(screen.getByRole("link", { name: "Mensal" })).toBeInTheDocument();
  });

  it("accordion: opening a sibling closes the other; header click closes the open one", () => {
    renderSidebar("/nowhere");
    fireEvent.click(trigger("Administracao"));
    fireEvent.click(trigger("Visao geral"));
    expect(expanded("Visao geral")).toBe("true");
    fireEvent.click(trigger("Clientes"));
    expect(expanded("Clientes")).toBe("true");
    expect(expanded("Visao geral")).toBe("false");
    // top level: opening Website closes Administracao
    fireEvent.click(trigger("Website"));
    expect(expanded("Administracao")).toBe("false");
    // closable
    fireEvent.click(trigger("Website"));
    expect(expanded("Website")).toBe("false");
    expect(screen.queryByRole("link", { name: "Docs" })).not.toBeInTheDocument();
  });

  it("auto-opens every group on the path to the current page", () => {
    renderSidebar("/admin/vendas/mensal");
    expect(expanded("Administracao")).toBe("true");
    expect(expanded("Visao geral")).toBe("true");
    expect(expanded("Relatorios")).toBe("true");
    expect(expanded("Clientes")).toBe("false");
    expect(expanded("Website")).toBe("false");
  });

  it("marks the L1 group active, emphasizes intermediates, leaf is aria-current", () => {
    renderSidebar("/admin/vendas/mensal");
    expect(trigger("Administracao")).toHaveAttribute("data-active", "true");
    expect(trigger("Visao geral")).toHaveAttribute("data-active", "true");
    expect(trigger("Clientes")).not.toHaveAttribute("data-active");
    expect(trigger("Website")).not.toHaveAttribute("data-active");
    expect(screen.getByRole("link", { name: "Mensal" })).toHaveAttribute("aria-current", "page");
  });

  it("only the most specific href is current (no prefix double-highlight)", () => {
    renderSidebar("/admin/vendas");
    expect(screen.getByRole("link", { name: "Vendas" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Admin Home" })).not.toHaveAttribute("aria-current");
  });

  it("parent href is current when it is the exact match", () => {
    renderSidebar("/admin");
    expect(screen.getByRole("link", { name: "Admin Home" })).toHaveAttribute("aria-current", "page");
  });

  it("respects a manual close until navigating into a different group", () => {
    const { rerender } = render(
      <MemoryRouter initialEntries={["/admin/usuarios"]}>
        <Sidebar brandIcon={Zap} brandTitle="T" brandSubtitle="S" navGroups={TREE} />
      </MemoryRouter>,
    );
    fireEvent.click(trigger("Administracao"));
    expect(expanded("Administracao")).toBe("false");
    rerender(
      <MemoryRouter initialEntries={["/admin/usuarios"]}>
        <Sidebar brandIcon={Zap} brandTitle="T" brandSubtitle="S" navGroups={TREE} />
      </MemoryRouter>,
    );
    expect(expanded("Administracao")).toBe("false");
  });

  it("backward compat: a flat group config renders unchanged", () => {
    const flat: NavGroup[] = [
      { key: "p", label: "Principal", icon, defaultOpen: true, items: [item("Dash", "/")] },
    ];
    renderSidebar("/nowhere", flat);
    expect(expanded("Principal")).toBe("false");
    fireEvent.click(trigger("Principal"));
    expect(screen.getByRole("link", { name: "Dash" })).toBeInTheDocument();
  });

  it("drops groups with no items at any level", () => {
    const g: NavGroup[] = [
      { key: "a", label: "Alpha", icon, items: [], groups: [{ key: "b", label: "Beta", icon, items: [] }] },
    ];
    renderSidebar("/", g);
    expect(screen.queryByRole("button", { name: "Alpha" })).not.toBeInTheDocument();
  });

  it("persists under a per-product storage key", () => {
    renderSidebar("/admin/usuarios", TREE, "orbity");
    expect(window.localStorage.getItem(sidebarStorageKey("orbity"))).not.toBeNull();
    expect(window.localStorage.getItem(sidebarStorageKey("igig"))).toBeNull();
    expect(sidebarStorageKey("orbity")).toBe("noctus.sidebar.openGroups.orbity");
  });

  it("group content carries the height/opacity animation classes and a reduced-motion opt-out", () => {
    renderSidebar("/nowhere");
    fireEvent.click(trigger("Administracao"));
    const content = screen.getByRole("link", { name: "Admin Home" }).closest("[data-state]") as HTMLElement;
    expect(content.getAttribute("data-state")).toBe("open");
    for (const c of [
      "data-[state=open]:animate-collapsible-down",
      "data-[state=closed]:animate-collapsible-up",
      "motion-reduce:animate-none",
    ]) {
      expect(content.className).toContain(c);
    }
    // overflow is only set inside the keyframes, never statically
    expect(content.className).not.toMatch(/overflow-hidden/);
  });
});
