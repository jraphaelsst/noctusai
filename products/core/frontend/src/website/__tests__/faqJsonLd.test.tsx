import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { SiteFaq } from "../components/SiteFaq";

const evil = "</script><script>window.__pwned=1</script>";

describe("SiteFaq JSON-LD", () => {
  // The organ's `Reveal` observes scroll position; jsdom has no IntersectionObserver / matchMedia.
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } });
    vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps an admin-edited </script> payload inert", () => {
    const { container } = render(<SiteFaq title="Perguntas" items={[{ q: { pt: "Q", en: "Q" }, a: { pt: evil, en: evil } } as never]} />);
    const scripts = container.querySelectorAll("script");
    expect(scripts).toHaveLength(1); // no injected second <script>
    const raw = scripts[0].innerHTML;
    // the visible answer is escaped text (React), never markup
    expect(container.querySelector("details p")?.textContent).toBe(evil);
    expect(raw).not.toContain("</script");
    expect(JSON.parse(raw).mainEntity[0].acceptedAnswer.text).toBe(evil);
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });
});
