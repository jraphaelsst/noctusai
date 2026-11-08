import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { renderToString } from "react-dom/server";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MotionProvider, Reveal, Stagger } from "./index";

function mockMatchMedia(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

/** jsdom has no IntersectionObserver; stub the browser boundary (in view = never fires). */
function stubIntersectionObserver() {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("marketing primitives", () => {
  it("server-renders content visible (no opacity:0, no JS needed)", () => {
    const html = renderToString(
      <MotionProvider>
        <Reveal>
          <p>reveal-text</p>
        </Reveal>
        <Stagger>
          <p>one</p>
          <p>two</p>
        </Stagger>
      </MotionProvider>,
    );
    expect(html).toContain("reveal-text");
    expect(html).toContain("one");
    expect(html).toContain("two");
    expect(html).not.toMatch(/opacity:\s*0(?![.\d])/);
  });

  it("under reduced motion nothing is hidden or moved after mount", async () => {
    mockMatchMedia(true);
    stubIntersectionObserver();
    await act(async () => {
      render(
        <MotionProvider>
          <Reveal>
            <p>calm</p>
          </Reveal>
          <Stagger>
            <p>calm-item</p>
          </Stagger>
        </MotionProvider>,
      );
    });
    for (const el of [screen.getByText("calm").parentElement!, screen.getByText("calm-item").parentElement!]) {
      expect(el.style.opacity === "" || el.style.opacity === "1").toBe(true);
      expect(el.style.transform === "" || el.style.transform === "none").toBe(true);
    }
  });

  it("with motion allowed, content stays in the DOM and is armed after mount", async () => {
    mockMatchMedia(false);
    stubIntersectionObserver();
    await act(async () => {
      render(
        <MotionProvider>
          <Reveal>
            <p>moving</p>
          </Reveal>
        </MotionProvider>,
      );
    });
    expect(screen.getByText("moving")).toBeInTheDocument();
  });
});

describe("motion is only reachable through the ./marketing subpath", () => {
  const srcRoot = path.resolve(__dirname, "..");
  const pkg = JSON.parse(readFileSync(path.resolve(srcRoot, "..", "package.json"), "utf-8"));

  function walk(dir: string, acc: string[] = []): string[] {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) walk(full, acc);
      else if (/\.tsx?$/.test(name) && !/\.test\./.test(name)) acc.push(full);
    }
    return acc;
  }

  it("no source outside src/marketing imports motion", () => {
    const offenders = walk(srcRoot)
      .filter((f) => !f.startsWith(path.join(srcRoot, "marketing") + path.sep))
      .filter((f) => /from\s+["'](motion|framer-motion)(\/[^"']*)?["']/.test(readFileSync(f, "utf-8")));
    expect(offenders).toEqual([]);
  });

  it("the root barrel does not re-export marketing", () => {
    expect(readFileSync(path.join(srcRoot, "index.ts"), "utf-8")).not.toMatch(/marketing/);
  });

  it("package.json exposes ./marketing and declares motion as a range peer", () => {
    expect(pkg.exports["./marketing"]).toBe("./src/marketing/index.ts");
    expect(pkg.peerDependencies.motion).toMatch(/^\^12/);
  });
});
