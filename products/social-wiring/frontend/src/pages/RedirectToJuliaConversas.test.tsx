/**
 * `/whatsapp-chat` back-compat redirect → `/julia/conversas`, carrying the
 * query string + hash.
 */
import { describe, it, expect, afterEach } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import RedirectToJuliaConversas from "./RedirectToJuliaConversas";

afterEach(() => cleanup());

function Landed() {
  const { pathname, search, hash } = useLocation();
  return <div data-testid="landed">{`${pathname}${search}${hash}`}</div>;
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/whatsapp-chat" element={<RedirectToJuliaConversas />} />
        <Route path="/julia/conversas" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RedirectToJuliaConversas", () => {
  it("redirects /whatsapp-chat to /julia/conversas", () => {
    expect(renderAt("/whatsapp-chat").getByTestId("landed").textContent).toBe("/julia/conversas");
  });

  it("preserves the query string and hash", () => {
    expect(renderAt("/whatsapp-chat?conn=c2#x").getByTestId("landed").textContent).toBe(
      "/julia/conversas?conn=c2#x",
    );
  });
});
