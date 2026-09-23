/**
 * `rolarAteAlvo` / `useRolarAteHash` — the readiness list's "Resolver" lands
 * on a CONTROL that usually mounts AFTER the jump (the subpage/page renders
 * first, its data after), so the target is polled for, never assumed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { rolarAteAlvo, useRolarAteHash } from "./useRolarAteAlvo";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(async () => {
  vi.useRealTimers();
  (await import("@testing-library/react")).cleanup();
  document.body.innerHTML = "";
});

function alvo(id: string) {
  const el = document.createElement("div");
  el.id = id;
  el.tabIndex = -1;
  el.scrollIntoView = vi.fn();
  return el;
}

describe("rolarAteAlvo", () => {
  it("🔴 waits for a target that mounts later, then scrolls to it and focuses it", () => {
    rolarAteAlvo("termos-ad-corpus-resposta");
    const el = alvo("termos-ad-corpus-resposta");
    vi.advanceTimersByTime(300);
    expect(el.scrollIntoView).not.toHaveBeenCalled(); // not in the DOM yet
    document.body.appendChild(el);
    vi.advanceTimersByTime(150);
    expect(el.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(el);
  });

  it("gives up quietly when the target never appears", () => {
    expect(() => {
      rolarAteAlvo("nunca", 3);
      vi.advanceTimersByTime(1000);
    }).not.toThrow();
  });

  it("the returned cleanup stops the polling", () => {
    const parar = rolarAteAlvo("depois");
    parar();
    const el = alvo("depois");
    document.body.appendChild(el);
    vi.advanceTimersByTime(500);
    expect(el.scrollIntoView).not.toHaveBeenCalled();
  });
});

describe("useRolarAteHash", () => {
  it("🔴 scrolls to the element the URL hash names (/imoveis/X#imovel-documentos)", async () => {
    const React = (await import("react")).default;
    const rtl = await import("@testing-library/react");
    const { MemoryRouter } = await import("react-router-dom");
    const el = alvo("imovel-documentos");
    document.body.appendChild(el);
    function Pagina() {
      useRolarAteHash();
      return null;
    }
    rtl.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/imoveis/IM-1#imovel-documentos"] },
        React.createElement(Pagina),
      ),
    );
    vi.advanceTimersByTime(10);
    expect(el.scrollIntoView).toHaveBeenCalled();
  });
});
