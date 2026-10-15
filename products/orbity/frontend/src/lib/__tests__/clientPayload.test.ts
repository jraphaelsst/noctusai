import { describe, it, expect } from "vitest";
import { clientPayload } from "../clientPayload";

describe("clientPayload", () => {
  it("omits empty email and zero due_date (backend 422s on both)", () => {
    const p = clientPayload({ name: " Ana ", email: "", phone: "", company: "", due_date: 0, monthly_value: 0, default_billing_type: "", billing_automation_enabled: false });
    expect(p).toEqual({ name: "Ana", billing_automation_enabled: false });
  });
  it("keeps valid values", () => {
    const p = clientPayload({ name: "A", email: "a@b.co", due_date: "15", monthly_value: "99.5", billing_automation_enabled: true });
    expect(p).toEqual({ name: "A", email: "a@b.co", due_date: 15, monthly_value: 99.5, billing_automation_enabled: true });
  });
  it("drops out-of-range due_date", () => {
    expect(clientPayload({ name: "A", due_date: 40 })).not.toHaveProperty("due_date");
  });
});
