/**
 * Tests for the runtime guard in `createProductApp`: calling without
 * EITHER a `supabase + useAuthStore` pair OR an `authProvider` must
 * throw a clear, actionable error — no silent fallback.
 *
 * Per `KB § 01-PHILOSOPHY § No silent errors`.
 */
import { describe, it, expect } from "vitest";
import { createProductApp } from "../src/app";

describe("createProductApp — error paths", () => {
  it("throws when neither authProvider nor supabase+useAuthStore are provided", () => {
    expect(() => {
      // @ts-expect-error — intentionally missing required config.
      createProductApp({});
    }).toThrowError(/authProvider.*supabase.*useAuthStore/);
  });

  it("throws when supabase is provided but useAuthStore is missing", () => {
    expect(() => {
      // @ts-expect-error — partial config to exercise the guard.
      createProductApp({ supabase: {} });
    }).toThrowError(/authProvider.*useAuthStore/);
  });

  it("throws when useAuthStore is provided but supabase is missing", () => {
    expect(() => {
      // @ts-expect-error — partial config to exercise the guard.
      createProductApp({ useAuthStore: () => ({}) });
    }).toThrowError(/authProvider.*supabase/);
  });
});
