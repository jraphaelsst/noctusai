import { describe, expect, it } from "vitest";

import { decidirMovimento, ehPendencias, ESTEIRA_ROLE_LABELS, permalinkValido } from "./moveRules";

const st = (papel: string | null, label = "E") => ({ label, papel });
const ctx = (direction: "forward" | "backward" | "same", from: string | null, to: string | null) => ({
  direction,
  fromStage: st(from),
  toStage: st(to),
});

describe("decidirMovimento (contract §4)", () => {
  it("reorder in the same column just proceeds", () => {
    expect(decidirMovimento(ctx("same", null, null))).toEqual({ tipo: "seguir" });
  });

  it("forward moves are free at any distance", () => {
    expect(decidirMovimento(ctx("forward", null, null))).toEqual({ tipo: "seguir" });
    expect(decidirMovimento(ctx("forward", null, "gravacao"))).toEqual({ tipo: "seguir" });
  });

  it("backward asks a reason", () => {
    const d = decidirMovimento(ctx("backward", null, null));
    expect(d).toMatchObject({ tipo: "motivo", titulo: "Por que este post está voltando?" });
  });

  it("into cancelado asks the block/cancel reason, even when moving 'forward'", () => {
    const d = decidirMovimento(ctx("forward", "gravacao", "cancelado"));
    expect(d).toMatchObject({ tipo: "motivo", titulo: "Motivo do bloqueio ou cancelamento" });
  });

  it("out of cancelado is a reactivation with a reason", () => {
    expect(decidirMovimento(ctx("backward", "cancelado", null))).toMatchObject({
      tipo: "motivo",
      titulo: "Reativar este post?",
    });
  });

  it("into postado asks the permalink", () => {
    expect(decidirMovimento(ctx("forward", null, "postado"))).toEqual({ tipo: "postado" });
  });

  it("labels the three roles", () => {
    expect(Object.keys(ESTEIRA_ROLE_LABELS).sort()).toEqual(["cancelado", "gravacao", "postado"]);
  });
});

describe("helpers", () => {
  it("detects the 409 pendencias body in its known shapes", () => {
    expect(ehPendencias({ body: { code: "pendencias" } })).toBe(true);
    expect(ehPendencias({ body: { detail: { code: "pendencias" } } })).toBe(true);
    expect(ehPendencias({ body: { error: { code: "pendencias" } } })).toBe(true);
    expect(ehPendencias(new Error("x"))).toBe(false);
  });

  it("accepts only blank or instagram.com permalinks", () => {
    expect(permalinkValido("")).toBe(true);
    expect(permalinkValido("https://www.instagram.com/reel/abc/")).toBe(true);
    expect(permalinkValido("https://evil.com/instagram.com")).toBe(false);
    expect(permalinkValido("nope")).toBe(false);
  });
});
