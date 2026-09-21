/**
 * ComoFunciona — `/como-funciona`, the seed `publicRoutes` slot.
 *
 * Covers the accordion's expand/collapse and the `#<id>` deep-link.
 * `@/lib/api` is mocked so the `InterestPopup` this page also mounts never
 * reaches the real seed infra.
 */
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import ComoFunciona from "../ComoFunciona";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  createInteressado: vi.fn(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/como-funciona" element={<ComoFunciona />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ComoFunciona", () => {
  it("renders every topic collapsed by default", () => {
    renderAt("/como-funciona");
    const trigger = screen.getByTestId("accordion-trigger-plano-diretor");
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    // Radix keeps the panel in the DOM (`hidden`), not unmounted — assert
    // visibility, not presence.
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("expands a section on click and collapses it again on a second click", () => {
    renderAt("/como-funciona");
    const trigger = screen.getByTestId("accordion-trigger-plano-diretor");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("accordion-panel-plano-diretor")).toBeVisible();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("expanding one section leaves the others collapsed (independent toggles, not an exclusive accordion)", () => {
    renderAt("/como-funciona");
    fireEvent.click(screen.getByTestId("accordion-trigger-plano-diretor"));
    expect(screen.getByTestId("accordion-panel-plano-diretor")).toBeVisible();
    expect(screen.getByTestId("accordion-panel-legislacao")).not.toBeVisible();
  });

  it("opens the deep-linked section via /como-funciona#<id> on mount", () => {
    renderAt("/como-funciona#legislacao");
    expect(screen.getByTestId("accordion-panel-legislacao")).toBeVisible();
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("renders every topic's numero + titulo", () => {
    renderAt("/como-funciona");
    expect(screen.getByText("Plano Diretor do Projeto")).toBeInTheDocument();
    expect(screen.getByText("Manifesto Fundador")).toBeInTheDocument();
  });

  it("shares the public-site nav (SiteHeader)", () => {
    renderAt("/como-funciona");
    expect(screen.getByTestId("link-a-carta")).toHaveAttribute("href", "/a-carta");
    expect(screen.getByTestId("link-entrar")).toHaveAttribute("href", "/login");
  });
});
