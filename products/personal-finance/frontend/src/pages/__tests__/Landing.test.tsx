/**
 * Landing page — static-content sanity test (PF Phase 6.c).
 *
 * Landing is intentionally static — no useQuery, no api calls. The test
 * just confirms the marketing copy renders + the call-to-action link
 * routes to /login.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Landing from "@/pages/Landing";

describe("Landing page (PF Phase 6.c — static)", () => {
  it("renders the PF brand title", () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );
    // PF Landing prominently uses "Financas Pessoais" or "Financas" in headings.
    const candidates = screen.queryAllByText(/Financ[aã]s/i);
    expect(candidates.length).toBeGreaterThan(0);
  });

  it("renders at least one router-dom Link to /login", () => {
    const { container } = render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );
    const anchors = Array.from(container.querySelectorAll("a"));
    const internal = anchors.filter((a) => a.getAttribute("href") === "/login");
    expect(internal.length).toBeGreaterThan(0);
  });
});
