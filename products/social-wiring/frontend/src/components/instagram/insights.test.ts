import { describe, expect, it } from "vitest";
import {
  followerGrowth,
  mediaKindLabel,
  pointsForPeriod,
  sortMetricsByPriority,
  sumMetric,
} from "./insights";

const pts = (rows: Array<[string, number | null, number | null]>) =>
  rows.map(([date, followers_count, views]) => ({ date, followers_count, views }));

describe("instagram insights helpers", () => {
  it("sorts metrics ascending by priority, stable on ties", () => {
    const sorted = sortMetricsByPriority([
      { key: "c", label: "C", format: "int", priority: 3 },
      { key: "a", label: "A", format: "int", priority: 1 },
      { key: "b2", label: "B2", format: "int", priority: 2 },
      { key: "b1", label: "B1", format: "int", priority: 2 },
    ]);
    expect(sorted.map((m) => m.key)).toEqual(["a", "b2", "b1", "c"]);
  });

  it("slices the period off the latest point; 'last' is one daily point", () => {
    const p = pts([
      ["2026-09-20", 10, 1],
      ["2026-09-30", 11, 2],
      ["2026-10-05", 12, 3],
      ["2026-10-06", 14, 4],
    ]);
    expect(pointsForPeriod(p, "7d").map((x) => x.date)).toEqual(["2026-09-30", "2026-10-05", "2026-10-06"]);
    expect(pointsForPeriod(p, "30d")).toHaveLength(4);
    expect(pointsForPeriod(p, "last").map((x) => x.date)).toEqual(["2026-10-06"]);
  });

  it("derives followers growth from deltas, null when not derivable", () => {
    const p = pts([
      ["2026-10-01", 100, null],
      ["2026-10-05", 110, null],
      ["2026-10-06", 115, null],
    ]);
    expect(followerGrowth(p, "30d")).toBe(15);
    expect(followerGrowth(p, "7d")).toBe(15);
    expect(followerGrowth(p, "last")).toBe(5);
    expect(followerGrowth(pts([["2026-10-06", 115, null]]), "30d")).toBeNull();
    expect(followerGrowth(pts([["2026-10-05", null, null], ["2026-10-06", 5, null]]), "30d")).toBeNull();
  });

  it("sums a metric but keeps null when never served (not 0)", () => {
    expect(sumMetric(pts([["2026-10-05", 1, 2], ["2026-10-06", 1, null]]), "views")).toBe(2);
    expect(sumMetric(pts([["2026-10-05", 1, null]]), "views")).toBeNull();
  });

  it("labels media kinds", () => {
    expect(mediaKindLabel({ media_type: "VIDEO", media_product_type: "REELS" })).toBe("Reel");
    expect(mediaKindLabel({ media_type: "CAROUSEL_ALBUM", media_product_type: "FEED" })).toBe("Carrossel");
    expect(mediaKindLabel({ media_type: "IMAGE", media_product_type: null })).toBe("Foto");
  });
});
