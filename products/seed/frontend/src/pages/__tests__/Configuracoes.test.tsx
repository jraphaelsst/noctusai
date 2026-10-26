/** Route test: `/configuracoes/*` -- the seed `SectionTabsPage` mount redirects the bare base to the first tab. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: (sel: (s: { user: { email: string } }) => unknown) => sel({ user: { email: "a@b.co" } }),
}));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<object>()),
  useEffectiveSSOContext: () => ({ org: { name: "Acme", role: "owner" } }),
}));

import Configuracoes from "../Configuracoes";

afterEach(cleanup);

describe("Configuracoes", () => {
  it("redirects the bare base to the Conta tab and shows the identity", () => {
    render(
      <MemoryRouter initialEntries={["/configuracoes"]}>
        <Routes><Route path="/configuracoes/*" element={<Configuracoes />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("section-panel-conta")).toBeInTheDocument();
    expect(screen.getByText("a@b.co")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });
});
