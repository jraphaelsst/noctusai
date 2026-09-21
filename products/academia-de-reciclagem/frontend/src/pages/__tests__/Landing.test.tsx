/**
 * Landing — the public page at `/` for signed-out visitors (seed `Landing` slot).
 *
 * Pins the two things this page owes the product: the designer's page renders
 * inside its style scope, and the "Entrar" link reaches the seed `/login` route.
 * jsdom has no IntersectionObserver (a browser API, not ours), so a minimal one
 * that reports every node as visible stands in for it.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Landing from "../Landing";

class VisibleIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  disconnect() {}
  unobserve() {}
  takeRecords() { return []; }
}

beforeEach(() => vi.stubGlobal("IntersectionObserver", VisibleIntersectionObserver));
afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Landing", () => {
  it("renders the designed page inside its style scope", () => {
    const { container } = renderAt("/");
    expect(container.firstElementChild).toHaveClass("academia-landing");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/O futuro se\s*separa agora\./);
    expect(screen.getByTestId("link-participar")).toHaveAttribute("href", "#participar");
  });

  it("'Entrar' takes the visitor to the seed login", () => {
    renderAt("/");
    const entrar = screen.getByTestId("link-entrar");
    expect(entrar).toHaveAttribute("href", "/login");
    fireEvent.click(entrar);
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("links the sponsor out in a new tab, without leaking the opener", () => {
    renderAt("/");
    const sponsor = screen.getByTestId("link-one-sponsor");
    expect(sponsor).toHaveAttribute("href", "https://oneconsultoriaimobiliaria.com.br/");
    expect(sponsor).toHaveAttribute("target", "_blank");
    expect(sponsor).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByTestId("link-pilares")).toHaveAttribute("href", "#pilares");
  });

  it("restores the page's scroll behaviour when it unmounts", () => {
    document.documentElement.style.scrollBehavior = "";
    const { unmount } = renderAt("/");
    expect(document.documentElement.style.scrollBehavior).toBe("smooth");
    unmount();
    expect(document.documentElement.style.scrollBehavior).toBe("");
  });
});
