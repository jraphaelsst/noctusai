/**
 * Coleta — `/coleta` + `/coleta/:municipio`, the seed `publicRoutes` slot.
 * Renders against the real transcribed data (`src/content/coleta/`); the
 * anchor fact is Carapicuíba's Fazendinha split (Setor 24 Seg/Qua/Sex vs
 * Setor 25 Ter/Qui/Sáb — prefeitura PDF of 2024-09-25).
 * `@/lib/api` is mocked so the `InterestPopup` never reaches the seed infra.
 */
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Coleta from "../Coleta";
import { MUNICIPIOS } from "@/content/coleta";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  createInteressado: vi.fn(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/coleta" element={<Coleta />} />
        <Route path="/coleta/:municipio" element={<Coleta />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Coleta", () => {
  it("lists every município as a shareable link", () => {
    renderAt("/coleta");
    for (const m of MUNICIPIOS) {
      expect(screen.getByTestId(`coleta-cidade-${m.slug}`)).toHaveAttribute("href", `/coleta/${m.slug}`);
    }
  });

  it("groups a city's schedule by day pattern, with sources collapsed", () => {
    renderAt("/coleta/carapicuiba");
    const painel = screen.getByTestId("coleta-municipio-carapicuiba");
    const dias = within(painel).getAllByTestId("coleta-grupo").map((g) => g.querySelector(".coleta-grupo-dias")?.textContent);
    expect(dias).toContain("Segunda, quarta e sexta");
    expect(dias).toContain("Terça, quinta e sábado");
    // 30 setores collapse to a handful of patterns.
    expect(dias.length).toBeLessThan(6);
    expect(within(painel).getByTestId("coleta-sobre")).not.toHaveAttribute("open");
  });

  it("every município declares at least one source (no unsourced schedule ships)", () => {
    for (const m of MUNICIPIOS) expect(m.fontes.length).toBeGreaterThan(0);
  });

  it("search answers in one line per kind of coleta", () => {
    renderAt("/coleta");
    fireEvent.change(screen.getByTestId("coleta-busca"), { target: { value: "Nova Fazendinha" } });
    const [primeiro] = screen.getAllByTestId("coleta-resultado");
    expect(primeiro).toHaveTextContent("Carapicuíba");
    expect(primeiro).toHaveTextContent("Lixo comum");
    expect(primeiro).toHaveTextContent("Seg · Qua · Sex, manhã e tarde");
  });

  it("a street split across setores shows both day-sets", () => {
    renderAt("/coleta");
    fireEvent.change(screen.getByTestId("coleta-busca"), { target: { value: "Estrada da Fazendinha" } });
    const textos = screen.getAllByTestId("coleta-resultado").map((c) => c.textContent ?? "");
    expect(textos.some((t) => t.includes("Seg · Qua · Sex"))).toBe(true);
    expect(textos.some((t) => t.includes("Ter · Qui · Sáb"))).toBe(true);
  });

  it("an unknown place offers the contribute link instead of an empty list", () => {
    renderAt("/coleta");
    fireEvent.change(screen.getByTestId("coleta-busca"), { target: { value: "zzzqqq" } });
    expect(screen.getByTestId("coleta-sem-resultado")).toHaveTextContent("conte pra gente");
  });

  it("an unknown município slug falls back to the list, not a blank page", () => {
    renderAt("/coleta/atlantida");
    expect(screen.getByText(/Ainda não temos "atlantida"/)).toBeInTheDocument();
  });

  it("shares the public-site nav, including the new coleta link", () => {
    renderAt("/coleta");
    expect(screen.getByTestId("link-coleta")).toHaveAttribute("href", "/coleta");
  });
});
