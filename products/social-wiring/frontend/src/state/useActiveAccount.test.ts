/**
 * `useActiveAccount` persist-migration tests.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Migration 046 renamed `clients` → `marcas` across this product, and the
 * codemod also rewrote `activeClientId` → `activeMarcaId` INSIDE the zustand
 * persist `migrate()` — the one place the old name is not ours to rename.
 * Every browser that has ever used this app holds a localStorage payload keyed
 * `activeClientId`; reading `activeMarcaId` from it yields `undefined`, so the
 * user's selected marca would be silently dropped on the first load after
 * deploy.
 *
 * Nothing caught it: `tsc` was clean (the key is optional), both suites were
 * green (no test read a pre-046 payload), and the diff looked like every other
 * line of the rename. It was found by reading the migration by hand.
 *
 * These tests pin the read side against payloads written by the OLD app, so a
 * future rename cannot quietly break the upgrade path again.
 */
import { describe, expect, it } from "vitest";

import { useActiveAccountStore } from "./useActiveAccount";

/** The `migrate` fn as zustand will call it, reached through the store options. */
const migrate = (
  useActiveAccountStore as unknown as {
    persist: { getOptions: () => { migrate: (p: unknown, v: number) => unknown } };
  }
).persist.getOptions().migrate;

describe("useActiveAccount — persist migration", () => {
  it("carries a v1 payload's activeClientId (the PRE-046 key) into activeMarcaId", () => {
    // Exactly what a browser running today's production build has stored.
    const stored = {
      activeAccountIdByProvider: { meta: "acc-1" },
      activeClientId: "c2b77620-c550-48e1-b789-b680c7e6bb0d",
    };
    const out = migrate(stored, 1) as { activeMarcaId: string | null };
    expect(out.activeMarcaId).toBe("c2b77620-c550-48e1-b789-b680c7e6bb0d");
  });

  it("preserves the per-provider account map across the v1 → v2 migration", () => {
    const out = migrate(
      { activeAccountIdByProvider: { meta: "acc-1" }, activeClientId: "x" },
      1,
    ) as { activeAccountIdByProvider: Record<string, string | null> };
    expect(out.activeAccountIdByProvider).toEqual({ meta: "acc-1" });
  });

  it("carries activeClientId through the v0 path too, dropping the unattributed account id", () => {
    const out = migrate(
      { activeAccountId: "bare-id", activeClientId: "marca-9" },
      0,
    ) as { activeMarcaId: string | null; activeAccountIdByProvider: Record<string, unknown> };
    expect(out.activeMarcaId).toBe("marca-9");
    // v0's bare id had no provider attribution — dropped rather than guessed.
    expect(out.activeAccountIdByProvider).toEqual({});
  });

  it("accepts a post-046 payload that already uses activeMarcaId", () => {
    const out = migrate(
      { activeAccountIdByProvider: {}, activeMarcaId: "marca-new" },
      1,
    ) as { activeMarcaId: string | null };
    expect(out.activeMarcaId).toBe("marca-new");
  });

  it("returns null rather than undefined when no selection was ever stored", () => {
    const out = migrate({ activeAccountIdByProvider: {} }, 1) as {
      activeMarcaId: string | null;
    };
    // null is the store's documented "org default" sentinel; undefined is not.
    expect(out.activeMarcaId).toBeNull();
  });
});
