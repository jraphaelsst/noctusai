/**
 * useMetaAds.test.ts — Cat B regression coverage: `placeholderData` on the
 * six filter/level/period-keyed queries in this file.
 *
 * `status`/`objective`/`level`/`since`/`until` all drive their respective
 * queryKeys (`K.campaigns` / `K.children` / `K.series` / `K.compare` /
 * the account-insights + activities keys), and every one of them is a
 * real UI-selectable value at the call sites (a status/objective filter
 * toggle, an adset/ad drill-down click, a date-range picker — see
 * `pages/meta/AdsVisaoGeral.tsx`'s `useDateRange`). Without
 * `placeholderData: (prev) => prev`, each of those UI actions swaps to a
 * fresh queryKey with no cached data, so `data` goes `undefined` and the
 * dashboard blanks for one round trip.
 *
 * Mock strategy mirrors `usePortalRoi.test.ts`: `@tanstack/react-query` is
 * fully mocked so `useQuery`'s call args (including `placeholderData`)
 * are directly inspectable without a live QueryClient/render.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  supabase: {},
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(() => ({ data: undefined, isPending: false, isFetching: false, isError: false }));
  const useMutation = vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useQuery as mockedUseQuery } from "@tanstack/react-query";
import {
  useAdsAccountInsights,
  useAdsActivities,
  useAdsCampaigns,
  useAdsChildren,
  useAdsInsightsCompare,
  useAdsInsightsSeries,
} from "./useMetaAds";

beforeEach(() => {
  vi.clearAllMocks();
});

function lastQueryCall() {
  return (mockedUseQuery as any).mock.calls.at(-1)[0];
}

function expectIdentityPlaceholderData() {
  const call = lastQueryCall();
  expect(typeof call.placeholderData).toBe("function");
  const prev = { sentinel: true };
  expect(call.placeholderData(prev)).toBe(prev);
}

describe("useMetaAds — placeholderData on filter/level/period-keyed queries", () => {
  it("🔴 useAdsCampaigns (status/objective filter)", () => {
    useAdsCampaigns("active", "leads");
    expectIdentityPlaceholderData();
  });

  it("🔴 useAdsChildren (adset/ad drill-down level)", () => {
    useAdsChildren("camp-1", "adset");
    expectIdentityPlaceholderData();
  });

  it("🔴 useAdsInsightsSeries (level/since/until/breakdown)", () => {
    useAdsInsightsSeries("camp-1", "campaign", "2026-07-01", "2026-07-31");
    expectIdentityPlaceholderData();
  });

  it("🔴 useAdsAccountInsights (since/until date range)", () => {
    useAdsAccountInsights("2026-07-01", "2026-07-31");
    expectIdentityPlaceholderData();
  });

  it("🔴 useAdsInsightsCompare (level/since/until)", () => {
    useAdsInsightsCompare("camp-1", "campaign", "2026-07-01", "2026-07-31");
    expectIdentityPlaceholderData();
  });

  it("🔴 useAdsActivities (since/until date range)", () => {
    useAdsActivities("2026-07-01", "2026-07-31");
    expectIdentityPlaceholderData();
  });
});
