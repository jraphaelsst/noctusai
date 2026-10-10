import { describe, it, expect } from "vitest";
import { PRIVACY_POLICY, CONSENT_META } from "../src/content/consent";

describe("privacy policy: Biblioteca de virais (Social Wiring)", () => {
  const sec = PRIVACY_POLICY.sections.find((s) => s.title.startsWith("Biblioteca de virais"));
  const text = JSON.stringify(sec);

  it("is present, with unique progressive section numbers", () => {
    expect(sec).toBeDefined();
    const ns = PRIVACY_POLICY.sections.map((s) => s.n);
    expect(ns).toEqual(ns.map((_, i) => String(i + 1)));
  });

  it("states legal basis, retention, sub-processor and the opt-out contact", () => {
    expect(text).toContain("art. 7º, IX");
    expect(text).toContain("90 dias");
    expect(text).toContain("Anthropic");
    expect(text).toContain("joaoraphaelsst@gmail.com");
  });

  it("bumps the displayed policy version", () => {
    expect(CONSENT_META.version).toBe("1.1");
  });
});
