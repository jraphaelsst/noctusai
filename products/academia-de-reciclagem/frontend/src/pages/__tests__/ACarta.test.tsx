/**
 * ACarta — `/a-carta`, the seed `publicRoutes` slot. Renders the letter's
 * title + body and styles the closing signature separately.
 * `@/lib/api` is mocked so the `InterestPopup` this page also mounts never
 * reaches the real seed infra.
 */
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";

import ACarta from "../ACarta";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  createInteressado: vi.fn(),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/a-carta"]}>
      <ACarta />
    </MemoryRouter>,
  );
}

describe("ACarta", () => {
  it("renders the letter's title", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Carta às Próximas Gerações");
  });

  it("styles the closing signature separately from the body", () => {
    renderPage();
    const signature = screen.getByTestId("carta-signature");
    expect(signature).toHaveTextContent("Gilson Tangerino");
    expect(signature).toHaveTextContent("Idealizador do Projeto Academia da Reciclagem.");
  });

  it("shares the public-site nav (SiteHeader): pages route, sections go back to the landing", () => {
    renderPage();
    expect(screen.getByTestId("link-projeto")).toHaveAttribute("href", "/o-projeto");
    expect(screen.getByTestId("link-a-carta")).toHaveAttribute("href", "/a-carta");
    // Off the landing, a section link becomes `/#<hash>` (SectionLink).
    expect(screen.getByTestId("link-como-funciona")).toHaveAttribute("href", "/#como-funciona");
  });
});
