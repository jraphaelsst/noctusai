import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import {
  RedirectJuliaPersonaToBia,
  RedirectJuliaToBia,
  RedirectLeadImobStudioToJulia,
} from "../LegacyRedirects";

function Where() {
  const { pathname, search, hash } = useLocation();
  return <div data-testid="where">{pathname + search + hash}</div>;
}

function at(initial: string) {
  render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/julia" element={<RedirectJuliaToBia />} />
        <Route path="/agentes/julia/persona" element={<RedirectJuliaPersonaToBia />} />
        <Route path="/studio/lead-imob" element={<RedirectLeadImobStudioToJulia />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByTestId("where").textContent;
}

describe("pre-rename routes redirect to their new homes", () => {
  it("/julia -> /bia", () => expect(at("/julia")).toBe("/bia"));
  it("/agentes/julia/persona -> /agentes/bia/persona", () =>
    expect(at("/agentes/julia/persona")).toBe("/agentes/bia/persona"));
  it("/studio/lead-imob -> /studio/julia, keeping the query and hash", () =>
    expect(at("/studio/lead-imob?tab=canais#x")).toBe("/studio/julia?tab=canais#x"));
});
