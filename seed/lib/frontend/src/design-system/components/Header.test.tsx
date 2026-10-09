/**
 * Header: the sign-out control's label is DERIVED from what `onLogout`
 * revokes (`logoutScope`), never free text — 2026-10-09, a hand-passed label
 * drifted across 5 core headers while every one of them revoked globally.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Header, LOGOUT_LABELS } from "./Header";
import type { HeaderProps } from "./Header";

afterEach(() => cleanup());

function renderHeader(props: Partial<HeaderProps> = {}) {
  render(
    <Header
      user={{ name: "Ana", email: "ana@x.com", role: "Administrador" }}
      onLogout={vi.fn()}
      theme="light"
      onThemeToggle={vi.fn()}
      {...props}
    />,
  );
  // The sign-out control lives in the profile HoverCard.
  const trigger = screen.getByText("Administrador").closest('div[class*="cursor-pointer"]') as HTMLElement;
  fireEvent.pointerEnter(trigger, { pointerType: "mouse" });
  fireEvent.mouseEnter(trigger);
  fireEvent.focus(trigger);
}

describe("Header sign-out label follows logoutScope", () => {
  it("defaults to global (supabase signOut's default) and says so", async () => {
    renderHeader();
    const el = await screen.findByLabelText(LOGOUT_LABELS.global);
    expect(el.getAttribute("title")).toBe("Sair de todos os dispositivos");
  });

  it("local scope reads plain 'Sair'", async () => {
    renderHeader({ logoutScope: "local" });
    expect(await screen.findByLabelText("Sair")).toBeTruthy();
  });

  it("redirect behaviour is labelled as navigation, not sign-out", async () => {
    renderHeader({ logoutBehavior: "redirect", platformUrl: "https://core.example" });
    expect(await screen.findByLabelText("Voltar ao NoctusAI")).toBeTruthy();
  });

  it("clicking the global control calls onLogout", async () => {
    const onLogout = vi.fn();
    renderHeader({ onLogout });
    fireEvent.click(await screen.findByLabelText(LOGOUT_LABELS.global));
    expect(onLogout).toHaveBeenCalledOnce();
  });
});
