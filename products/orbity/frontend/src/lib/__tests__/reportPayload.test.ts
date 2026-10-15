import { describe, it, expect } from "vitest";
import { describePayload, formatPayloadValue } from "../reportPayload";

describe("describePayload", () => {
  it("renders meta_ads block and scope as items, never raw JSON", () => {
    const items = describePayload({
      leads: 4, revenues: 1000, expenses: 200, scope: "client",
      meta_ads: { spend: 300, leads: 10, cpl: 30, active_campaigns: 2 },
    });
    const keys = items.map((i) => i.key);
    expect(keys).toEqual(["leads", "revenues", "expenses", "meta_spend", "meta_leads", "meta_cpl", "meta_active", "scope"]);
    expect(formatPayloadValue(items.find((i) => i.key === "scope")!)).toBe("Cliente");
  });
  it("expenses {available:false} becomes an Indisponível item with the reason", () => {
    const [item] = describePayload({ expenses: { available: false, reason: "Despesas não são por cliente" } });
    expect(item.kind).toBe("unavailable");
    expect(formatPayloadValue(item)).toBe("Indisponível");
    expect(item.hint).toBe("Despesas não são por cliente");
  });
});
