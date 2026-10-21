/** NotificationBell -- a notification that carries an in-app link opens it (marks read, closes, navigates). */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotificationBell, notificationLink, notificationProduct, withNextPath } from "./NotificationBell";

const base = { org_id: "o", user_id: "u", tipo: "system", titulo: "Aviso", is_read: false, created_at: "2026-10-20T10:00:00Z" };

function hooks(items: unknown[], marcar = vi.fn()) {
  return {
    useNotificacoes: () => ({ data: { data: items as never[] } }),
    useContagemNaoLidas: () => ({ data: { nao_lidas: items.length } }),
    useMarcarComoLida: () => ({ mutate: marcar, isPending: false }),
    useMarcarTodasComoLidas: () => ({ mutate: vi.fn(), isPending: false }),
  };
}
afterEach(() => cleanup());

describe("notificationLink", () => {
  it("reads link, else metadata.link, same-origin paths only", () => {
    expect(notificationLink({ link: "/a" })).toBe("/a");
    expect(notificationLink({ metadata: { link: "/b?x=1" } })).toBe("/b?x=1");
    expect(notificationLink({ link: "//evil.example" })).toBeNull();
    expect(notificationLink({ link: "https://evil.example" })).toBeNull();
    expect(notificationLink({})).toBeNull();
  });
});

describe("NotificationBell link click", () => {
  it("navigates to the link and marks the notification read", () => {
    const marcar = vi.fn();
    const onNavigate = vi.fn();
    render(<NotificationBell hooks={hooks([{ ...base, id: "n1", metadata: { link: "/opt-outs?evento=e1" } }], marcar)} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByLabelText("Notificacoes"));
    fireEvent.click(screen.getByTestId("notificacao-n1"));
    expect(onNavigate).toHaveBeenCalledWith("/opt-outs?evento=e1");
    expect(marcar).toHaveBeenCalledWith("n1");
  });

  it("is inert without onNavigate or without a link", () => {
    const onNavigate = vi.fn();
    render(<NotificationBell hooks={hooks([{ ...base, id: "n2" }])} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByLabelText("Notificacoes"));
    fireEvent.click(screen.getByTestId("notificacao-n2"));
    expect(onNavigate).not.toHaveBeenCalled();
  });
});

describe("cross-product notices", () => {
  const item = (extra: Record<string, unknown>) => ({ ...base, id: "x1", ...extra });
  const open = () => { fireEvent.click(screen.getByLabelText("Notificacoes")); };

  it("same product: in-app navigate, no label", () => {
    const onNavigate = vi.fn(); const onNavigateProduct = vi.fn();
    render(<NotificationBell hooks={hooks([item({ metadata: { product: "agents", link: "/a" } })])} currentProduct="agents" onNavigate={onNavigate} onNavigateProduct={onNavigateProduct} />);
    open();
    expect(screen.queryByTestId("notificacao-produto-x1")).toBeNull();
    fireEvent.click(screen.getByTestId("notificacao-x1"));
    expect(onNavigate).toHaveBeenCalledWith("/a");
    expect(onNavigateProduct).not.toHaveBeenCalled();
  });

  it("no metadata.product: in-app navigate", () => {
    const onNavigate = vi.fn(); const onNavigateProduct = vi.fn();
    render(<NotificationBell hooks={hooks([item({ link: "/b" })])} currentProduct="agents" onNavigate={onNavigate} onNavigateProduct={onNavigateProduct} />);
    open(); fireEvent.click(screen.getByTestId("notificacao-x1"));
    expect(onNavigate).toHaveBeenCalledWith("/b");
    expect(onNavigateProduct).not.toHaveBeenCalled();
  });

  it("other product: labelled, marks read, opens in the owning product", () => {
    const marcar = vi.fn(); const onNavigate = vi.fn(); const onNavigateProduct = vi.fn();
    render(<NotificationBell hooks={hooks([item({ metadata: { product: "social-wiring", link: "/julia/opt-outs?evento=e1" } })], marcar)} currentProduct="agents" onNavigate={onNavigate} onNavigateProduct={onNavigateProduct} />);
    open();
    expect(screen.getByTestId("notificacao-produto-x1").textContent).toBe("social-wiring");
    fireEvent.click(screen.getByTestId("notificacao-x1"));
    expect(onNavigateProduct).toHaveBeenCalledWith("social-wiring", "/julia/opt-outs?evento=e1");
    expect(onNavigate).not.toHaveBeenCalled();
    expect(marcar).toHaveBeenCalledWith("x1");
  });

  it("unknown product (handler rejects): no navigation, still marked read, no throw", async () => {
    const marcar = vi.fn(); const onNavigate = vi.fn();
    const onNavigateProduct = vi.fn().mockRejectedValue(new Error("404"));
    render(<NotificationBell hooks={hooks([item({ metadata: { product: "nope", link: "/x" } })], marcar)} currentProduct="agents" onNavigate={onNavigate} onNavigateProduct={onNavigateProduct} />);
    open(); fireEvent.click(screen.getByTestId("notificacao-x1"));
    await Promise.resolve(); await Promise.resolve();
    expect(onNavigate).not.toHaveBeenCalled();
    expect(marcar).toHaveBeenCalledWith("x1");
  });

  it("absolute URL link: refused, not clickable", () => {
    const onNavigate = vi.fn(); const onNavigateProduct = vi.fn();
    render(<NotificationBell hooks={hooks([item({ metadata: { product: "social-wiring", link: "https://evil.example/x" } })])} currentProduct="agents" onNavigate={onNavigate} onNavigateProduct={onNavigateProduct} />);
    open(); fireEvent.click(screen.getByTestId("notificacao-x1"));
    expect(onNavigate).not.toHaveBeenCalled();
    expect(onNavigateProduct).not.toHaveBeenCalled();
  });

  it("malformed product slug is ignored (treated as no product)", () => {
    expect(notificationProduct({ metadata: { product: "https://evil" } })).toBeNull();
    expect(notificationProduct({ metadata: { product: "social-wiring" } })).toBe("social-wiring");
  });
});

describe("withNextPath", () => {
  it("adds next to the fragment (strict) or query (legacy); refuses non-paths and non-http urls", () => {
    expect(withNextPath("https://sw.example/sso#token=t", "/julia/opt-outs?evento=1")).toBe("https://sw.example/sso#token=t&next=%2Fjulia%2Fopt-outs%3Fevento%3D1");
    expect(withNextPath("https://sw.example/sso?token=t", "/a")).toBe("https://sw.example/sso?token=t&next=%2Fa");
    expect(withNextPath("https://sw.example/sso#token=t", "https://evil.example")).toBeNull();
    expect(withNextPath("https://sw.example/sso#token=t", "//evil.example")).toBeNull();
    expect(withNextPath("javascript:alert(1)", "/a")).toBeNull();
  });
});
