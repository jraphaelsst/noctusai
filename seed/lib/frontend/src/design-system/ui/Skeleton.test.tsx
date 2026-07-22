/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Skeleton } from "./Skeleton";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Installs a `window.matchMedia` stub reporting a fixed `matches` value for every query. */
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  );
}

describe("Skeleton", () => {
  it("renders a single status announcement by default", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status", { name: "Carregando" })).toBeInTheDocument();
  });

  it("accepts a custom accessible label", () => {
    render(<Skeleton label="Carregando tabela" />);
    expect(screen.getByRole("status", { name: "Carregando tabela" })).toBeInTheDocument();
  });

  it("renders as aria-hidden decorative (no status role) when announce=false", () => {
    const { container } = render(<Skeleton announce={false} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("pulses (animate-pulse) when the system has no reduced-motion preference", () => {
    stubMatchMedia(false);
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveClass("animate-pulse");
  });

  it("suppresses the pulse animation when prefers-reduced-motion is set", () => {
    stubMatchMedia(true);
    const { container } = render(<Skeleton />);
    expect(container.firstChild).not.toHaveClass("animate-pulse");
    // Still renders — reduced motion means "no animation," not "no skeleton."
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("degrades gracefully (still pulses) when matchMedia is unavailable", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveClass("animate-pulse");
  });

  it("applies the requested rounded variant", () => {
    const { container } = render(<Skeleton rounded="full" />);
    expect(container.firstChild).toHaveClass("rounded-full");
  });

  it("applies fixed width/height as inline style", () => {
    const { container } = render(<Skeleton width={120} height="2rem" />);
    expect(container.firstChild).toHaveStyle({ width: "120px", height: "2rem" });
  });
});
