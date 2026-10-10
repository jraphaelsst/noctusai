import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import RedirectMediaCreation from "./RedirectMediaCreation";

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/media-creation" element={<RedirectMediaCreation />} />
        <Route path="/media-creation/carrosseis" element={<p>carrosseis</p>} />
        <Route path="/media-creation/branding" element={<p>branding</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RedirectMediaCreation", () => {
  it("sends the legacy page to Carrosséis", () => {
    renderAt("/media-creation");
    expect(screen.getByText("carrosseis")).toBeTruthy();
  });

  it("sends the legacy Branding tab to the Branding page", () => {
    renderAt("/media-creation?tab=brand");
    expect(screen.getByText("branding")).toBeTruthy();
  });
});
