import { describe, expect, it } from "vitest";
import { lerDecimalBR } from "./moedaDecimal";

describe("lerDecimalBR", () => {
  it.each([
    ["6,26", "6.26"],
    ["6.26", "6.26"],
    ["6", "6"],
    [" 6,5 ", "6.5"],
    ["", ""],
  ])("%j -> %j", (i, o) => expect(lerDecimalBR(i)).toBe(o));
  it.each(["abc", "6,2,6", "1.234,5", "-1", "6%"])("rejeita %j", (i) =>
    expect(lerDecimalBR(i)).toBeNull(),
  );
});
