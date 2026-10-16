import { describe, it, expect } from "vitest";
import { clientPayload, documentDigits, isCnpj } from "../clientPayload";

describe("clientPayload", () => {
  it("omits empty email and zero due_date (backend 422s on both)", () => {
    const p = clientPayload({ legal_name: " Ana LTDA ", name: "", email: "", phone: "", due_date: 0, monthly_value: 0, default_billing_type: "", billing_automation_enabled: false });
    expect(p).toEqual({ legal_name: "Ana LTDA", billing_automation_enabled: false });
  });
  it("keeps valid values", () => {
    const p = clientPayload({ legal_name: "A LTDA", name: "A", email: "a@b.co", due_date: "15", monthly_value: "99.5", billing_automation_enabled: true });
    expect(p).toEqual({ legal_name: "A LTDA", name: "A", email: "a@b.co", due_date: 15, monthly_value: 99.5, billing_automation_enabled: true });
  });
  it("drops out-of-range due_date", () => {
    expect(clientPayload({ legal_name: "A", due_date: 40 })).not.toHaveProperty("due_date");
  });
  it("omits an empty nome fantasia so the server falls back to the legal name", () => {
    expect(clientPayload({ legal_name: "Acme Comércio LTDA", name: "   " })).not.toHaveProperty("name");
  });
  it("sends the CPF/CNPJ as typed (the server validates and normalises it)", () => {
    expect(clientPayload({ legal_name: "A", document: " 11.222.333/0001-81 " })).toMatchObject({ document: "11.222.333/0001-81" });
    expect(clientPayload({ legal_name: "A", document: "" })).not.toHaveProperty("document");
  });
});

describe("document helpers", () => {
  it("strips the mask and recognises a CNPJ by its 14 digits", () => {
    expect(documentDigits("11.222.333/0001-81")).toBe("11222333000181");
    expect(isCnpj("11.222.333/0001-81")).toBe(true);
    expect(isCnpj("123.456.789-09")).toBe(false);
  });
});
