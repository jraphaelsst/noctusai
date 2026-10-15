import { describe, it, expect } from "vitest";
import { approvalPublicUrl, reportPublicUrl, approvalPublicPath } from "../publicLinks";

describe("public links", () => {
  it("approval link points at the SPA page, not the /api surface", () => {
    expect(approvalPublicUrl("tok-1", "https://app.test")).toBe("https://app.test/aprovar/tok-1");
    expect(approvalPublicUrl("tok-1", "https://app.test")).not.toContain("/api/");
  });
  it("report link points at /relatorio/:token", () => {
    expect(reportPublicUrl("abc", "https://app.test")).toBe("https://app.test/relatorio/abc");
  });
  it("encodes the token and defaults to window origin", () => {
    expect(approvalPublicPath("a b")).toBe("/aprovar/a%20b");
    expect(reportPublicUrl("x")).toBe(`${window.location.origin}/relatorio/x`);
  });
});
