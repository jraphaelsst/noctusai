/** A daily-limit 429 offers "Ajustar limites" (→ Configurações → Limites diários) to owner/admin only. */
import * as rtl from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const sso = vi.hoisted(() => ({ role: "owner" }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<object>()),
  useEffectiveSSOContext: () => ({ org: { role: sso.role } }),
}));

import { toast } from "sonner";
import { LinkAjustarLimites, useToastErroGeracao } from "./LimiteDiarioAviso";

const limite = { status: 429, message: "[429] x" };

beforeEach(() => {
  vi.clearAllMocks();
  sso.role = "owner";
});

function toastCom(err: unknown) {
  const { result } = rtl.renderHook(() => useToastErroGeracao());
  result.current("Limite diário atingido", err);
}

describe("LimiteDiarioAviso", () => {
  it.each(["owner", "admin"])("a 429 for an %s carries the Ajustar limites action", (role) => {
    sso.role = role;
    toastCom(limite);
    const [msg, opts] = (toast.error as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(msg).toBe("Limite diário atingido");
    expect(opts.action.label).toBe("Ajustar limites");
  });

  it("a member gets the plain message", () => {
    sso.role = "member";
    toastCom(limite);
    expect(toast.error).toHaveBeenCalledWith("Limite diário atingido");
  });

  it("any other error is a plain message, even for the owner", () => {
    toastCom({ status: 500 });
    expect(toast.error).toHaveBeenCalledWith("Limite diário atingido");
  });

  it("the inline link points to the settings section, for admins only", () => {
    const r = rtl.render(<MemoryRouter><LinkAjustarLimites /></MemoryRouter>);
    expect(r.getByTestId("link-ajustar-limites").getAttribute("href")).toBe("/configuracoes/limites");
    r.unmount();
    sso.role = "member";
    const r2 = rtl.render(<MemoryRouter><LinkAjustarLimites /></MemoryRouter>);
    expect(r2.queryByTestId("link-ajustar-limites")).toBeNull();
  });
});
