/**
 * `env.CORE_APP_HOME` — core's logged-in dashboard (`CORE_URL` + `/painel`).
 * Derived from CORE_URL so a deploy never sets two vars that can disagree.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { env } from "./env";

afterEach(() => vi.restoreAllMocks());

describe("env.CORE_APP_HOME", () => {
  it("is CORE_URL + /painel", () => {
    vi.spyOn(env, "CORE_URL", "get").mockReturnValue("https://noctusai.com");
    expect(env.CORE_APP_HOME).toBe("https://noctusai.com/painel");
  });

  it("does not double the slash when CORE_URL has a trailing slash", () => {
    vi.spyOn(env, "CORE_URL", "get").mockReturnValue("https://core.noctusai.com/");
    expect(env.CORE_APP_HOME).toBe("https://core.noctusai.com/painel");
  });

  it("derives from the real CORE_URL (house-port dev default when unset)", () => {
    expect(env.CORE_APP_HOME).toBe(`${env.CORE_URL}/painel`);
  });
});
