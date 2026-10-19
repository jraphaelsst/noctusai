/**
 * `/whatsapp-chat` back-compat redirect → `/lais/conversas`, carrying the
 * query string + hash.
 */
import { describe, it, expect, afterEach } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import RedirectToLaisConversas from "./RedirectToLaisConversas";

afterEach(() => cleanup());

function Landed() {
  const { pathname, search, hash } = useLocation();
  return <div data-testid="landed">{`${pathname}${search}${hash}`}</div>;
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/whatsapp-chat" element={<RedirectToLaisConversas />} />
        <Route path="/lais/conversas" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RedirectToLaisConversas", () => {
  it("redirects /whatsapp-chat to /lais/conversas", () => {
    expect(renderAt("/whatsapp-chat").getByTestId("landed").textContent).toBe("/lais/conversas");
  });

  it("preserves the query string and hash", () => {
    expect(renderAt("/whatsapp-chat?conn=c2#x").getByTestId("landed").textContent).toBe(
      "/lais/conversas?conn=c2#x",
    );
  });
});
