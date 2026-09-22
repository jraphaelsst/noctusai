/**
 * `/como-funciona` → `/o-projeto` — the compatibility redirect.
 *
 * The old path is in the wild (shared links, the landing's earlier
 * "Ver como funciona" button), so it must keep landing on the page rather
 * than 404-ing. The deep-link hash has to survive the hop too: it is what
 * opens the matching topic on arrival.
 */
import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import ComoFuncionaRedirect from "../ComoFuncionaRedirect";

function Destination() {
  const { pathname, hash } = useLocation();
  return <div data-testid="destination">{`${pathname}${hash}`}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/como-funciona" element={<ComoFuncionaRedirect />} />
        <Route path="/o-projeto" element={<Destination />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ComoFuncionaRedirect", () => {
  it("sends /como-funciona to /o-projeto", () => {
    renderAt("/como-funciona");
    expect(screen.getByTestId("destination")).toHaveTextContent("/o-projeto");
  });

  it("carries the deep-link hash across", () => {
    renderAt("/como-funciona#plano-diretor");
    expect(screen.getByTestId("destination")).toHaveTextContent("/o-projeto#plano-diretor");
  });
});
