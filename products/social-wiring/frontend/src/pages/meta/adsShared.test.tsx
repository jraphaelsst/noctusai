/**
 * `rowLeads` — the BE/FE seam for Meta's two lead action keys.
 *
 * Pinned because this helper silently under-counted for as long as it
 * existed: it was `actions["lead"] ?? actions["onsite_conversion.lead"]`,
 * first-key-wins, which drops the second capture channel whenever a row
 * carries both. It read as correct because the pilot account populates only
 * `onsite_conversion.lead`, where `??` and `+` agree — so no fixture ever
 * disagreed with production.
 *
 * Must stay in lockstep with the backend's
 * `meta_ads/services/leads.py::leads_from_actions`.
 */
import { describe, it, expect } from "vitest";

import { rowLeads } from "./adsShared";
import type { AdsInsightsRow } from "@/hooks/useMetaAds";

function row(actions: Record<string, number>): AdsInsightsRow {
  return {
    date: "2026-08-31",
    spend_cents: 0,
    impressions: 0,
    reach: 0,
    clicks: 0,
    cpc_cents: null,
    cpm_cents: null,
    ctr: null,
    actions,
    action_values: {},
    breakdown: {},
  };
}

describe("rowLeads", () => {
  it("sums BOTH lead keys — they are distinct capture channels, not aliases", () => {
    // The regression: `??` returned 5 here and dropped the Instant-Form 3.
    expect(rowLeads(row({ lead: 5, "onsite_conversion.lead": 3 }))).toBe(8);
  });

  it("counts the off-Facebook pixel/CAPI key alone", () => {
    expect(rowLeads(row({ lead: 4 }))).toBe(4);
  });

  it("counts the native Instant-Form key alone (the pilot account's shape)", () => {
    expect(rowLeads(row({ "onsite_conversion.lead": 7 }))).toBe(7);
  });

  it("reports 0 when neither key is present — never a fabricated value", () => {
    expect(rowLeads(row({ link_click: 12 }))).toBe(0);
  });

  it("tolerates a row with no actions object at all", () => {
    const bare = { ...row({}), actions: undefined as unknown as Record<string, number> };
    expect(rowLeads(bare)).toBe(0);
  });
});
