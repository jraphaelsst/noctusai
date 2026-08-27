/**
 * Tests for the AppShell desktop hover rail + the Sidebar's icon-only rendering.
 *
 * The invariant these exist to protect is the OVERLAY CONTRACT: expanding the
 * rail must never change the layout. A width transition is easy to eyeball and
 * easy to regress (one `md:relative` reintroduced and `main` starts reflowing
 * on every hover), so the slot width is asserted mechanically here.
 *
 * Coverage:
 *   1. Layout slot reserves the COLLAPSED width and does not change on expand
 *   2. Rail expands on pointer hover and collapses on leave
 *   3. Rail expands on keyboard focus (focus-within parity — not optional)
 *   4. Hover and focus are independent (leaving the pointer keeps a focused
 *      rail open)
 *   5. `railMode="expanded"` escape hatch restores the static 256px sidebar
 *   6. Collapsed rows keep their accessible name + gain a title tooltip
 *   7. Mobile drawer is untouched (base `w-64`, translate driven by the header)
 *
 * Dual-React gap: resolved in this package (NOC-REMEDIATE[harness-vitest-dual-react]
 * RESOLVED 2026-05-29) — full render tests are safe.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Home, LayoutDashboard, Users, Zap } from "lucide-react";

import { AppShell } from "./AppShell";
import { Sidebar } from "./Sidebar";
import type { NavGroup } from "./Sidebar";

afterEach(cleanup);

const NAV_GROUPS: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Equipe", href: "/equipe", icon: Users, badge: 3 },
    ],
  },
];

function renderShell(railMode?: "hover-expand" | "expanded") {
  const view = render(
    <MemoryRouter>
      <AppShell
        railMode={railMode}
        sidebar={
          <Sidebar
            brandIcon={Zap}
            brandTitle="NoctusAI"
            brandSubtitle="Testes"
            navGroups={NAV_GROUPS}
          />
        }
        header={({ onMenuToggle }) => (
          <button onClick={onMenuToggle}>menu</button>
        )}
      >
        <p>conteudo</p>
      </AppShell>
    </MemoryRouter>,
  );

  const aside = view.container.querySelector("aside");
  const slot = view.container.querySelector('div[aria-hidden="true"]');
  if (!aside || !slot) throw new Error("AppShell must render an <aside> and a layout slot");
  return { ...view, aside, slot };
}

/** React's enter/leave plugin is driven by mouseover/mouseout, not mouseenter. */
const hover = (el: Element) => fireEvent.mouseOver(el);
const unhover = (el: Element) => fireEvent.mouseOut(el);

/**
 * React 17+ implements `onFocus`/`onBlur` on the native BUBBLING `focusin` /
 * `focusout` pair (that is what makes them focus-within-equivalent). A raw
 * `el.focus()` is also not act()-wrapped, so its state update would not flush
 * before the assertion — fireEvent is.
 */
/**
 * 🔴 jsdom DOES NOT IMPLEMENT `:focus-visible` (2026-08-27).
 *
 * The shell asks `target.matches(':focus-visible')` to tell a KEYBOARD focus
 * from focus that merely landed there after a mouse click — the browser's own
 * heuristic, and the only thing that stops a click on a nav item pinning the
 * rail open over the page it just navigated to.
 *
 * jsdom answers `false` for every element, keyboard or not, so a test cannot
 * reach the keyboard branch without standing in for that heuristic. These two
 * helpers do exactly that and nothing else: `keyboardFocusIn` makes the target
 * report `:focus-visible`, `pointerFocusIn` makes it deny it. Both go through
 * the same `focusIn` event, because the DISTINCTION under test is the selector
 * answer, not the event.
 *
 * Stubbing per-element (not `Element.prototype`) keeps the fake scoped to the
 * one node the test focuses, so nothing leaks into a sibling assertion.
 */
function focusInAs(el: Element, focusVisible: boolean) {
  const real = el.matches.bind(el);
  Object.defineProperty(el, "matches", {
    configurable: true,
    value: (selector: string) =>
      selector === ":focus-visible" ? focusVisible : real(selector),
  });
  fireEvent.focusIn(el);
}

const keyboardFocusIn = (el: Element) => focusInAs(el, true);
const pointerFocusIn = (el: Element) => focusInAs(el, false);
const focusIn = keyboardFocusIn;
const focusOut = (el: Element) => fireEvent.focusOut(el);

/** `md:overflow-hidden` contains the substring "hidden" — match the utility. */
const hasDisplayHidden = (className: string) => /(^|\s)(\w+:)?hidden(\s|$)/.test(className);

describe("AppShell hover rail", () => {
  it("reserves the collapsed width in the layout slot and never changes it on expand", () => {
    const { aside, slot } = renderShell();

    expect(slot.className).toContain("w-16");
    expect(slot.className).not.toContain("w-64");

    hover(aside);

    // 🔴 The overlay contract: the slot is byte-identical after expansion, so
    // `main` cannot reflow. Only the (fixed-position) aside grows.
    expect(slot.className).toContain("w-16");
    expect(slot.className).not.toContain("w-64");
    expect(aside.className).toContain("md:w-64");
  });

  it("expands on hover and collapses on leave", () => {
    const { aside } = renderShell();

    expect(aside.className).toContain("md:w-16");
    expect(aside).toHaveAttribute("data-rail-expanded", "false");

    hover(aside);
    expect(aside.className).toContain("md:w-64");
    expect(aside.className).not.toContain("md:w-16");
    expect(aside).toHaveAttribute("data-rail-expanded", "true");

    unhover(aside);
    expect(aside.className).toContain("md:w-16");
    expect(aside).toHaveAttribute("data-rail-expanded", "false");
  });

  it("expands on keyboard focus so tabbing never lands on invisible labels", () => {
    const { aside } = renderShell();

    const link = screen.getByRole("link", { name: "Dashboard" });
    focusIn(link);
    expect(aside).toHaveAttribute("data-rail-expanded", "true");

    focusOut(link);
    expect(aside).toHaveAttribute("data-rail-expanded", "false");
  });

  it("keeps the rail open when the pointer leaves while focus is still inside", () => {
    const { aside } = renderShell();

    hover(aside);
    focusIn(screen.getByRole("link", { name: "Dashboard" }));

    unhover(aside);
    expect(aside).toHaveAttribute("data-rail-expanded", "true");
  });

  it("does NOT stay open when focus arrived from a MOUSE CLICK", () => {
    // 🔴 THE PROD BUG (2026-08-27). This shipped using `focusin` alone, which
    // fires for a click too — so clicking a nav item left focus sitting on it
    // and pinned the rail open ACROSS the page the click had just navigated
    // to. It only closed when something else happened to take focus. Found by
    // clicking through the deployed app, not by any test.
    const { aside } = renderShell();
    const link = screen.getByRole("link", { name: "Dashboard" });

    hover(aside);
    pointerFocusIn(link);
    unhover(aside);

    expect(aside).toHaveAttribute("data-rail-expanded", "false");
  });

  it("still expands for a KEYBOARD focus on the same element", () => {
    // The other half of the same rule: narrowing to `:focus-visible` must not
    // cost the keyboard path, or tabbing lands on clipped labels again.
    const { aside } = renderShell();

    keyboardFocusIn(screen.getByRole("link", { name: "Dashboard" }));
    expect(aside).toHaveAttribute("data-rail-expanded", "true");
  });

  it('railMode="expanded" restores the static 256px sidebar', () => {
    const { aside, slot } = renderShell("expanded");

    expect(slot.className).toContain("w-64");
    expect(aside.className).toContain("md:w-64");
    expect(aside).not.toHaveAttribute("data-rail-expanded");

    hover(aside);
    expect(slot.className).toContain("w-64");
    expect(aside.className).toContain("md:w-64");
  });

  it("keeps the mobile drawer contract (full width + header-driven translate)", () => {
    const { aside } = renderShell();

    // Base (mobile) width is unconditional — the rail is a `md:` affordance.
    expect(aside.className).toContain("w-64");
    expect(aside.className).toContain("-translate-x-full");

    fireEvent.click(screen.getByRole("button", { name: "menu" }));
    expect(aside.className).toContain("translate-x-0");
    expect(aside.className).not.toContain("-translate-x-full");
  });
});

describe("Sidebar collapsed rendering", () => {
  it("preserves accessible names and adds a title tooltip while collapsed", () => {
    const { aside } = renderShell();

    // Collapsed: the name survives (opacity/max-width collapse, never `display`).
    const link = screen.getByRole("link", { name: "Dashboard" });
    expect(link).toHaveAttribute("title", "Dashboard");

    hover(aside);
    // Expanded: still named, tooltip dropped (it would be noise next to the label).
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("title");
  });

  it("collapses labels via max-width, not display, so they animate instead of popping", () => {
    const { aside } = renderShell();

    const label = screen.getByText("Dashboard");
    expect(label.className).toContain("md:max-w-0");
    expect(label.className).toContain("md:opacity-0");
    expect(hasDisplayHidden(label.className)).toBe(false);

    hover(aside);
    expect(screen.getByText("Dashboard").className).not.toContain("md:max-w-0");
  });

  it("renders nav destinations in the collapsed rail (group open-state untouched)", () => {
    renderShell();

    // `defaultOpen` group stays open while collapsed — the rail shows the
    // destination icons, not just category headers.
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Equipe" })).toBeInTheDocument();
  });

  it("renders unchanged outside an AppShell (context default is not-a-rail)", () => {
    render(
      <MemoryRouter>
        <Sidebar
          brandIcon={Zap}
          brandTitle="NoctusAI"
          brandSubtitle="Testes"
          navGroups={NAV_GROUPS}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "Dashboard" });
    expect(link).not.toHaveAttribute("title");
    expect(screen.getByText("Dashboard").className).not.toContain("md:max-w-0");
  });
});
