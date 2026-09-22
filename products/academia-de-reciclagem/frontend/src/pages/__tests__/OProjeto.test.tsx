/**
 * OProjeto — `/o-projeto`, the seed `publicRoutes` slot.
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

import OProjeto from "../OProjeto";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  createInteressado: vi.fn(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/o-projeto" element={<OProjeto />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OProjeto", () => {
  it("renders every topic collapsed by default", () => {
    renderAt("/o-projeto");
    const trigger = screen.getByTestId("accordion-trigger-plano-diretor");
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    // Radix keeps the panel in the DOM (`hidden`), not unmounted — assert
    // visibility, not presence.
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("expands a section on click and collapses it again on a second click", () => {
    renderAt("/o-projeto");
    const trigger = screen.getByTestId("accordion-trigger-plano-diretor");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("accordion-panel-plano-diretor")).toBeVisible();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("expanding one section leaves the others collapsed (independent toggles, not an exclusive accordion)", () => {
    renderAt("/o-projeto");
    fireEvent.click(screen.getByTestId("accordion-trigger-plano-diretor"));
    expect(screen.getByTestId("accordion-panel-plano-diretor")).toBeVisible();
    expect(screen.getByTestId("accordion-panel-legislacao")).not.toBeVisible();
  });

  it("opens the deep-linked section via /o-projeto#<id> on mount", () => {
    renderAt("/o-projeto#legislacao");
    expect(screen.getByTestId("accordion-panel-legislacao")).toBeVisible();
    expect(screen.getByTestId("accordion-panel-plano-diretor")).not.toBeVisible();
  });

  it("renders every topic's numero + titulo", () => {
    renderAt("/o-projeto");
    expect(screen.getByText("Plano Diretor do Projeto")).toBeInTheDocument();
    expect(screen.getByText("Manifesto Fundador")).toBeInTheDocument();
  });

  it("shares the public-site nav (SiteHeader)", () => {
    renderAt("/o-projeto");
    expect(screen.getByTestId("link-a-carta")).toHaveAttribute("href", "/a-carta");
    expect(screen.getByTestId("link-entrar")).toHaveAttribute("href", "/login");
  });

  it("carries no images in the article body — the reading page is text only", () => {
    const { container } = renderAt("/o-projeto");
    // Scoped to the topic list, NOT the whole page: the shared SiteHeader
    // legitimately carries the brand logo. What must be gone is the
    // "30 toneladas" infographic that used to interrupt the prose — it
    // now has its own landing section.
    const article = container.querySelector(".accordion-list");
    expect(article).not.toBeNull();
    expect(article!.querySelectorAll("img")).toHaveLength(0);
    expect(article!.querySelectorAll("figure")).toHaveLength(0);
  });
});
