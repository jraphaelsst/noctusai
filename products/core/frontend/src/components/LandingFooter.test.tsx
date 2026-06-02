/**
 * LandingFooter — verifies the three consent links render with correct hrefs.
 * Uses react-router MemoryRouter so Link resolution works without a full app.
 */
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LandingFooter } from "./LandingFooter";

afterEach(() => cleanup());

describe("LandingFooter", () => {
  function renderFooter() {
    return render(
      <MemoryRouter>
        <LandingFooter />
      </MemoryRouter>
    );
  }

  it("renders the Central de Privacidade link to /consent", () => {
    const { getByText } = renderFooter();
    const link = getByText("Central de Privacidade").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/consent");
  });

  it("renders Política de Privacidade link to /consent/privacy-policy", () => {
    const { getByText } = renderFooter();
    const link = getByText("Política de Privacidade").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/consent/privacy-policy");
  });

  it("renders Termos de Uso link to /consent/terms-of-use", () => {
    const { getByText } = renderFooter();
    const link = getByText("Termos de Uso").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/consent/terms-of-use");
  });

  it("renders all three consent links", () => {
    const { getByText } = renderFooter();
    expect(getByText("Central de Privacidade")).toBeTruthy();
    expect(getByText("Política de Privacidade")).toBeTruthy();
    expect(getByText("Termos de Uso")).toBeTruthy();
  });
});
