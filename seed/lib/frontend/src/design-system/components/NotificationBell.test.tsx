/** NotificationBell -- a notification that carries an in-app link opens it (marks read, closes, navigates). */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotificationBell, notificationLink } from "./NotificationBell";

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
