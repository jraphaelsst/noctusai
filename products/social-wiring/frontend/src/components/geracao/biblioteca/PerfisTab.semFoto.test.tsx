/** A member's profile card: handle + name only — null photo and null followers must render cleanly. */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { PerfilCard } from "./PerfisTab";
import type { PerfilBiblioteca } from "@/types/bibliotecaPlataforma";

const base: PerfilBiblioteca = {
  id: "p1", handle: "criador", nome: "Criador", foto_url: null, seguidores: null, status: "ativo", erro_mensagem: null,
  ultima_sync_em: null, metrica_base: null, mediana_metrica: null, virais: 0, posts: 0, ingestao_ativa: true, optout_contato: "x@y.z",
  monitorar: true, estruturas_total: 0,
};

describe("PerfilCard (member view)", () => {
  it("shows initials and no follower line when photo and followers are null", () => {
    render(<MemoryRouter><PerfilCard perfil={{ ...base, estruturas_total: undefined as never }} /></MemoryRouter>);
    expect(screen.queryByText(/seguidores/)).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("cr")).toBeTruthy();
    expect(screen.getByText("@criador")).toBeTruthy();
  });

  it("a member's card (admin keys absent) renders no status or Somente biblioteca badge", () => {
    const { status: _s, monitorar: _m, ultima_sync_em: _u, ...semAdmin } = base;
    render(<MemoryRouter><PerfilCard perfil={semAdmin as never} /></MemoryRouter>);
    expect(screen.queryByText("Ativo")).toBeNull();
    expect(screen.queryByText("Somente biblioteca")).toBeNull();
  });

  it("an admin still sees the status", () => {
    render(<MemoryRouter><PerfilCard perfil={base} /></MemoryRouter>);
    expect(screen.getByText("Ativo")).toBeTruthy();
  });

  it("keeps the estruturas count without the follower figure", () => {
    render(<MemoryRouter><PerfilCard perfil={{ ...base, estruturas_total: 3 }} /></MemoryRouter>);
    expect(screen.getByText("3 estruturas")).toBeTruthy();
    expect(screen.queryByText(/seguidores/)).toBeNull();
  });
});
