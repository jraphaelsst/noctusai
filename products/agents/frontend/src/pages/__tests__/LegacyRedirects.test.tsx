/** Old routes -> the unified agent page (agents-unified CONTRACT §7), query + hash kept. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import {
  RedirectAcademiaChat,
  RedirectAgentePersona,
  RedirectCatalogo,
  RedirectJuliaPersonaToBia,
  RedirectLeadImobStudioToJulia,
  RedirectStudio,
  RedirectStudioAgent,
} from "../LegacyRedirects";

function Where() {
  const { pathname, search, hash } = useLocation();
  return <div data-testid="where">{pathname + search + hash}</div>;
}

function at(initial: string) {
  render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/bia" element={<RedirectAcademiaChat />} />
        <Route path="/julia" element={<RedirectAcademiaChat />} />
        <Route path="/agentes/catalogo" element={<RedirectCatalogo />} />
        <Route path="/agentes/julia/persona" element={<RedirectJuliaPersonaToBia />} />
        <Route path="/agentes/:key/persona" element={<RedirectAgentePersona />} />
        <Route path="/studio" element={<RedirectStudio />} />
        <Route path="/studio/lead-imob" element={<RedirectLeadImobStudioToJulia />} />
        <Route path="/studio/:key" element={<RedirectStudioAgent />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByTestId("where").textContent;
}

describe("old agent shells redirect to /agentes/:key", () => {
  it("/studio/:key -> /agentes/:key, keeping the deep-link query and hash", () =>
    expect(at("/studio/isaia?tab=prompt&secao=abc#x")).toBe("/agentes/isaia?tab=prompt&secao=abc#x"));
  it("/agentes/:key/persona -> ?tab=persona", () => expect(at("/agentes/bia/persona")).toBe("/agentes/bia?tab=persona"));
  it("/agentes/catalogo -> /agentes", () => expect(at("/agentes/catalogo")).toBe("/agentes"));
  it("/studio (the former console) -> /agentes, where its actions now live", () => expect(at("/studio")).toBe("/agentes"));
  it("/bia -> the academia agent's chat section", () => expect(at("/bia")).toBe("/agentes/bia?tab=conversar"));
});

describe("pre-rename routes", () => {
  it("/julia -> /agentes/bia?tab=conversar", () => expect(at("/julia")).toBe("/agentes/bia?tab=conversar"));
  it("/agentes/julia/persona -> /agentes/bia?tab=persona", () =>
    expect(at("/agentes/julia/persona")).toBe("/agentes/bia?tab=persona"));
  it("/studio/lead-imob -> /agentes/julia, keeping the query and hash", () =>
    expect(at("/studio/lead-imob?tab=canais#x")).toBe("/agentes/julia?tab=canais#x"));
});
