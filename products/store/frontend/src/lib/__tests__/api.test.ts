import { describe, it, expect, vi } from "vitest";

vi.mock("@noctusai/seed/infra", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), upload: vi.fn() } }));

import { centsFromDigits, centsToMask, formatBRL, formatBRLShort, isValidCpf, isValidEmail, maskCpf } from "@/lib/api";

describe("store api helpers", () => {
  it("masks a CPF progressively", () => {
    expect(maskCpf("123")).toBe("123");
    expect(maskCpf("1234")).toBe("123.4");
    expect(maskCpf("1234567")).toBe("123.456.7");
    expect(maskCpf("12345678901")).toBe("123.456.789-01");
    expect(maskCpf("123.456.789-01999")).toBe("123.456.789-01");
  });

  it("validates CPF check digits", () => {
    expect(isValidCpf("529.982.247-25")).toBe(true);
    expect(isValidCpf("529.982.247-24")).toBe(false);
    expect(isValidCpf("111.111.111-11")).toBe(false);
    expect(isValidCpf("123")).toBe(false);
  });

  it("validates e-mail", () => {
    expect(isValidEmail("a@b.co")).toBe(true);
    expect(isValidEmail("a@b")).toBe(false);
  });

  it("formats BRL", () => {
    expect(formatBRL(4700)).toBe("R$ 47,00");
    expect(formatBRLShort(4700)).toBe("R$ 47");
    expect(formatBRLShort(4750)).toBe("R$ 47,50");
  });

  it("converts the BRL input mask to cents and back", () => {
    expect(centsFromDigits("47,00")).toBe(4700);
    expect(centsFromDigits("")).toBe(0);
    expect(centsToMask(4700)).toBe("47,00");
  });
});
