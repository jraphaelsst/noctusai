import { describe, expect, it, vi } from "vitest";
import * as rtl from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

vi.mock("./Chat", () => ({ default: () => <p>chat-secao</p> }));
vi.mock("./HeadlinesGerar", () => ({ default: () => <p>gerar-secao</p> }));
vi.mock("./HeadlinesFavoritas", () => ({ default: () => <p>favoritas-secao</p> }));
vi.mock("./HeadlinesSugeridas", () => ({ default: () => <p>sugeridas-secao</p> }));
vi.mock("./Roteiros", () => ({ default: () => <p>meus-secao</p> }));
vi.mock("./HeadlinesRoteiros", () => ({ default: () => <p>hr-secao</p> }));
const visivel = vi.hoisted(() => vi.fn((_: string) => true));
vi.mock("@/hooks/geracao/usePaginaVisivel", () => ({ usePaginaVisivel: () => visivel }));

import RoteirosHub from "./RoteirosHub";
import { RedirectHeadlinesFavoritas, RedirectMeusRoteiros } from "./redirectsRoteiros";

function Onde() {
  const l = useLocation();
  return <span data-testid="onde">{l.pathname + l.search}</span>;
}

function renderAt(url: string) {
  return rtl.render(
    <MemoryRouter initialEntries={[url]}>
      <Onde />
      <Routes>
        <Route path="/media-creation/chat/*" element={<RoteirosHub />} />
        <Route path="/media-creation/headlines/favoritas" element={<RedirectHeadlinesFavoritas />} />
        <Route path="/media-creation/roteiros" element={<RedirectMeusRoteiros />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RoteirosHub", () => {
  it("the bare path lands on the Roteiro tab and keeps the query", async () => {
    renderAt("/media-creation/chat?c=c1");
    expect(await rtl.screen.findByText("chat-secao")).toBeTruthy();
    expect(rtl.screen.getByTestId("onde").textContent).toBe("/media-creation/chat/roteiro?c=c1");
  });

  it("offers every tab, in order, with one h1", async () => {
    renderAt("/media-creation/chat/roteiro");
    await rtl.screen.findByText("chat-secao");
    const tabs = rtl.screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["Roteiro", "Gerar Headlines", "Headlines Favoritas", "Headlines sugeridas", "Meus Roteiros", "Headlines e Roteiros"]);
    expect(rtl.screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("hides a tab whose status_pagina key is not visible", async () => {
    visivel.mockImplementation((r: string) => r !== "media-creation-roteiros");
    renderAt("/media-creation/chat/roteiro");
    await rtl.screen.findByText("chat-secao");
    expect(rtl.screen.queryByRole("tab", { name: "Meus Roteiros" })).toBeNull();
    visivel.mockImplementation(() => true);
  });

  it("an old URL redirects to its tab, keeping ?hid", async () => {
    renderAt("/media-creation/headlines/favoritas?hid=h1");
    expect(await rtl.screen.findByText("favoritas-secao")).toBeTruthy();
    expect(rtl.screen.getByTestId("onde").textContent).toBe("/media-creation/chat/favoritas?hid=h1");
  });

  it("the old Meus roteiros URL keeps ?open", async () => {
    renderAt("/media-creation/roteiros?open=r1");
    expect(await rtl.screen.findByText("meus-secao")).toBeTruthy();
    expect(rtl.screen.getByTestId("onde").textContent).toBe("/media-creation/chat/meus-roteiros?open=r1");
  });
});
