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
  it("expenses {available:false} becomes an Indisponível item with a pt-BR reason (internal)", () => {
    const [item] = describePayload({ expenses: { available: false, reason: "expenses are not attributed to clients" } });
    expect(item.kind).toBe("unavailable");
    expect(formatPayloadValue(item)).toBe("Indisponível");
    expect(item.hint).toBe("Despesas não são vinculadas a clientes — veja o relatório da agência.");
  });
  it("unknown backend reasons never leak raw", () => {
    const [item] = describePayload({ expenses: { available: false, reason: "some english dev string" } });
    expect(item.hint).toBe("Não disponível para este escopo.");
  });
  it("public audience drops unavailable metrics, scope and snapshot metadata", () => {
    const items = describePayload(
      { expenses: { available: false, reason: "x" }, scope: "client", generated_at: "2026-10-15T20:17:26Z", meta_ads: { spend: 120 } },
      { audience: "public" },
    );
    expect(items.map((i) => i.key)).toEqual(["meta_spend"]);
  });
  it("snapshot metadata keys never become tiles (internal either)", () => {
    const items = describePayload({ generated_at: "2026-10-15T20:17:26Z", period_start: "2026-10-01", leads: 1 });
    expect(items.map((i) => i.key)).toEqual(["leads"]);
  });
});
