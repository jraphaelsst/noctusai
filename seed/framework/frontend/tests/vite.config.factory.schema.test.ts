/**
 * Tests for `resolveProductSchema` — the SPA's Supabase client must target
 * the SAME schema the product's backend owns. The prior `?? "public"`
 * default pointed every SPA at `public`, so the layout's
 * `.from('status_pagina')` 404'd fleet-wide (found live on igig, 2026-09-23).
 */
import fs from "fs";
import os from "os";
import path from "path";
import { describe, it, expect } from "vitest";

import { resolveProductSchema } from "../vite.config.factory";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function productFrontend(slug: string): string {
  return path.join(REPO_ROOT, "products", slug, "frontend");
}

function tempProduct(databasePy: string | null): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "vite-schema-"));
  const frontend = path.join(root, "frontend");
  fs.mkdirSync(frontend);
  if (databasePy !== null) {
    fs.mkdirSync(path.join(root, "backend/app"), { recursive: true });
    fs.writeFileSync(path.join(root, "backend/app/database.py"), databasePy);
  }
  return frontend;
}

describe("resolveProductSchema", () => {
  it("an explicit schema wins over derivation", () => {
    expect(resolveProductSchema(productFrontend("igig"), "custom")).toBe("custom");
  });

  it("derives from create_database_module(..., schema=...)", () => {
    const dir = tempProduct('_db = create_database_module(settings, schema="igig")\n');
    expect(resolveProductSchema(dir, undefined)).toBe("igig");
  });

  it("derives from a module-level SCHEMA constant", () => {
    const dir = tempProduct('from x import y\n\nSCHEMA = "p_studio"\n');
    expect(resolveProductSchema(dir, undefined)).toBe("p_studio");
  });

  it("keeps hyphenated schema names intact", () => {
    const dir = tempProduct('db = create_database_module(settings, schema="personal-finance")\n');
    expect(resolveProductSchema(dir, undefined)).toBe("personal-finance");
  });

  it("throws instead of silently defaulting to public when nothing is derivable", () => {
    expect(() => resolveProductSchema(tempProduct(null), undefined)).toThrow(/cannot derive the product schema/);
    expect(() => resolveProductSchema(tempProduct("# no schema here\n"), undefined)).toThrow(
      /cannot derive the product schema/,
    );
  });

  it("every real product frontend resolves to its backend's schema (never a silent public)", () => {
    const expected: Record<string, string> = {
      igig: "igig",
      "p-studio": "p_studio",
      "erp-imobiliario": "erp",
      orbity: "orbity",
      "academia-de-reciclagem": "academia_de_reciclagem",
      "social-wiring": "social_wiring",
      agents: "agents",
      community: "community",
      seed: "seed",
      core: "public",
    };
    for (const [slug, schema] of Object.entries(expected)) {
      expect(resolveProductSchema(productFrontend(slug), undefined), slug).toBe(schema);
    }
  });
});
