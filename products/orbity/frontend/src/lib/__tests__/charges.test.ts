import { describe, it, expect } from "vitest";
import { chargeBanner, gatewayCancelNote, formatCents, formatDay } from "../charges";

const base = { generation_attempts: 1, last_error: null, next_attempt_at: null, entry_status: "open" as const };

describe("chargeBanner", () => {
  it("queued / generating are in-flight and cannot be re-queued", () => {
    expect(chargeBanner({ ...base, generation_status: "queued" })).toMatchObject({ status: "queued", tone: "neutral", canRequeue: false });
    expect(chargeBanner({ ...base, generation_status: "generating" })).toMatchObject({ status: "generating", tone: "progress", canRequeue: false });
  });

  it("retrying shows the attempt, the last error and when the next attempt is", () => {
    const b = chargeBanner({ ...base, generation_status: "retrying", generation_attempts: 3, last_error: "timeout calling /payments", next_attempt_at: "2026-10-16T15:30:00+00:00" });
    expect(b.tone).toBe("warning");
    expect(b.title).toContain("tentativa 3");
    expect(b.detail).toContain("timeout calling /payments");
    expect(b.detail).toContain("Próxima tentativa");
    expect(b.canRequeue).toBe(false);
  });

  it("generated is a success with nothing to redo", () => {
    expect(chargeBanner({ ...base, generation_status: "generated" })).toMatchObject({ tone: "success", canRequeue: false, detail: null });
  });

  it("failed carries the last error and offers a retry while the receivable is open", () => {
    const b = chargeBanner({ ...base, generation_status: "failed", last_error: "Cliente sem CPF/CNPJ" });
    expect(b).toMatchObject({ tone: "danger", detail: "Cliente sem CPF/CNPJ", canRequeue: true });
  });

  it("failed on a receivable that is no longer open offers nothing", () => {
    expect(chargeBanner({ ...base, entry_status: "paid", generation_status: "failed", last_error: "x" }).canRequeue).toBe(false);
  });

  it("skipped is an honest plain receivable and says why", () => {
    const b = chargeBanner({ ...base, generation_status: "skipped", last_error: "Gateway de cobrança não configurado para esta organização." });
    expect(b.title).toMatch(/sem cobrança no gateway/i);
    expect(b.detail).toContain("não configurado");
    expect(b.canRequeue).toBe(true);
  });
});

describe("gatewayCancelNote", () => {
  it("is silent when there is nothing to cancel at the gateway", () => {
    expect(gatewayCancelNote({ gateway_cancel_status: null, gateway_cancel_error: null })).toBeNull();
    expect(gatewayCancelNote({ gateway_cancel_status: "done", gateway_cancel_error: null })).toBeNull();
  });
  it("reports a pending cancel and a failed one with the reason", () => {
    expect(gatewayCancelNote({ gateway_cancel_status: "pending", gateway_cancel_error: null })).toMatch(/pendente/);
    expect(gatewayCancelNote({ gateway_cancel_status: "failed", gateway_cancel_error: "A cobrança já foi paga no gateway" })).toContain("já foi paga");
  });
});

describe("formatting", () => {
  it("formats cents as BRL and dates as pt-BR without a timezone shift", () => {
    expect(formatCents(150050).replace(/\s/g, " ")).toBe("R$ 1.500,50");
    expect(formatDay("2026-10-05")).toBe("05/10/2026");
    expect(formatDay(null)).toBe("—");
  });
});
