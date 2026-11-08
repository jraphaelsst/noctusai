/**
 * Disabled / badged nav (2026-11-08) + canonical module-group ordering.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Home } from "lucide-react";

import { Sidebar } from "./Sidebar";
import type { NavGroup } from "./Sidebar";
import { MODULE_GROUP_ORDER, MODULE_GROUP_LABELS, orderNavGroups } from "./nav-groups";

afterEach(cleanup);
beforeEach(() => window.localStorage.clear());

const icon = Home;
const item = (name: string, href: string, extra: object = {}) => ({ name, href, icon, ...extra });

function renderSidebar(groups: NavGroup[], path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar
        brandIcon={Home}
        brandTitle="T"
        brandSubtitle="S"
        navGroups={groups}
        storageKey="disabled-test"
      />
    </MemoryRouter>,
  );
}

const GROUPS: NavGroup[] = [
  {
    key: "crm",
    label: "CRM",
    icon,
    items: [
      item("Leads", "/leads"),
      item("Funil", "/leads/funil", { disabled: true, badge: "Em breve" }),
    ],
  },
];

describe("Sidebar disabled item", () => {
  it("is not a link, has aria-disabled, and renders the badge", () => {
    renderSidebar(GROUPS, "/leads");
    const row = screen.getByText("Funil").closest("[aria-disabled]");
    expect(row).toHaveAttribute("aria-disabled", "true");
    expect(row?.tagName).not.toBe("A");
    expect(screen.queryByRole("link", { name: "Funil" })).toBeNull();
    expect(screen.getByText("Em breve")).toBeInTheDocument();
  });

  it("is skipped by active-path matching (parent stays the current page)", () => {
    renderSidebar(GROUPS, "/leads/funil");
    expect(screen.getByRole("link", { name: "Leads" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Funil").closest("[aria-current]")).toBeNull();
  });

  it("enabled items are unchanged (still links)", () => {
    renderSidebar(GROUPS, "/x");
    fireEvent.click(screen.getByRole("button", { name: "CRM" }));
    expect(screen.getByRole("link", { name: "Leads" })).toHaveAttribute("href", "/leads");
  });
});

describe("Sidebar disabled group", () => {
  const G: NavGroup[] = [
    {
      key: "cms",
      label: "CMS",
      icon,
      disabled: true,
      badge: "Em breve",
      items: [item("Páginas", "/paginas")],
    },
  ];

  it("shows the chip on the header and still expands to disabled children", () => {
    renderSidebar(G, "/paginas");
    expect(screen.getByText("Em breve")).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "CMS" });
    // Disabled items are never current, so nothing auto-opens: expand by hand.
    if (trigger.getAttribute("aria-expanded") !== "true") fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const row = screen.getByText("Páginas").closest("[aria-disabled]");
    expect(row).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("link", { name: "Páginas" })).toBeNull();
  });
});

describe("orderNavGroups", () => {
  const g = (key: string) => ({ key });
  it("orders known keys canonically, unknown keep relative order, nothing dropped", () => {
    const out = orderNavGroups([g("zeta"), g("erp"), g("alpha"), g("crm"), g("configuracoes")]);
    expect(out.map((x) => x.key)).toEqual(["crm", "erp", "configuracoes", "zeta", "alpha"]);
  });
  it("does not mutate input and honours a custom order", () => {
    const input = [g("b"), g("a")];
    expect(orderNavGroups(input, ["a"]).map((x) => x.key)).toEqual(["a", "b"]);
    expect(input.map((x) => x.key)).toEqual(["b", "a"]);
  });
  it("labels every canonical key", () => {
    for (const k of MODULE_GROUP_ORDER) expect(MODULE_GROUP_LABELS[k]).toBeTruthy();
    expect(MODULE_GROUP_LABELS.emissoes).toBe("Emissões");
  });
});
