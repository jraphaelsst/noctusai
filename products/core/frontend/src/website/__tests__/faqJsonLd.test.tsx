import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { FaqAccordion } from "../components/FaqAccordion";

const evil = "</script><script>window.__pwned=1</script>";

describe("FaqAccordion JSON-LD", () => {
  it("keeps an admin-edited </script> payload inert", () => {
    const { container } = render(<FaqAccordion items={[{ q: { pt: "Q", en: "Q" }, a: { pt: evil, en: evil } } as never]} />);
    const scripts = container.querySelectorAll("script");
    expect(scripts).toHaveLength(1); // no injected second <script>
    const raw = scripts[0].innerHTML;
    expect(raw).not.toContain("</script");
    expect(JSON.parse(raw).mainEntity[0].acceptedAnswer.text).toBe(evil);
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });
});
