import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BackToCore } from "../src/components/BackToCore";
import { PRODUCT_LANDING_PATH, goToProductLanding } from "../src/product-landing";

describe("goToProductLanding", () => {
  it("navigates to the product's own root (relative: stays on the product origin)", () => {
    const navigate = vi.fn();
    goToProductLanding(navigate);
    expect(navigate).toHaveBeenCalledWith("/");
    expect(PRODUCT_LANDING_PATH).toBe("/");
  });

  it.each(["https://agents.noctusai.com", "https://noctusai.com", "https://erp.noctusai.com"])(
    "resolves against %s, never against core",
    (origin) => {
      const navigate = vi.fn((url: string) => {
        expect(new URL(url, origin).origin).toBe(origin);
      });
      goToProductLanding(navigate);
      expect(navigate).toHaveBeenCalledTimes(1);
    },
  );
});

describe("BackToCore", () => {
  it("is icon-only, named by aria-label + title, and points at the given href", () => {
    render(<BackToCore href="https://noctusai.com/painel" />);
    const link = screen.getByRole("link", { name: "Voltar ao NoctusAI" });
    expect(link.getAttribute("href")).toBe("https://noctusai.com/painel");
    expect(link.getAttribute("title")).toBe("Voltar ao NoctusAI");
    expect(link.textContent).toBe("");
    expect(link.querySelector("svg")).toBeTruthy();
    expect(link.className).toContain("focus-visible:ring-2");
    expect(link.className).toContain("h-8");
  });
});
