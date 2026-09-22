/**
 * Landing — the public page at `/` for signed-out visitors (seed `Landing` slot).
 *
 * Pins the two things this page owes the product: the designer's page renders
 * inside its style scope, and the "Entrar" link reaches the seed `/login` route.
 * jsdom has no IntersectionObserver (a browser API, not ours), so a minimal one
 * that reports every node as visible stands in for it.
 *
 * Also covers the shared `SiteHeader` nav (the `/o-projeto` and
 * `/a-carta` links) and `InterestPopup`, both mounted by `Landing` —
 * `@/lib/api` is mocked so the popup's `createInteressado` call never
 * reaches the real seed infra.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@noctusai/lib";

import Landing from "../Landing";

const mockCreateInteressado = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  createInteressado: (input: unknown) => mockCreateInteressado(input),
}));

const POPUP_DELAY_MS = 4000;

class VisibleIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  disconnect() {}
  unobserve() {}
  takeRecords() { return []; }
}

beforeEach(() => vi.stubGlobal("IntersectionObserver", VisibleIntersectionObserver));
afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Landing", () => {
  it("renders the designed page inside its style scope", () => {
    const { container } = renderAt("/");
    expect(container.firstElementChild).toHaveClass("academia-landing");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/O futuro se\s*separa agora\./);
    expect(screen.getByTestId("link-participar")).toHaveAttribute("href", "#participar");
  });

  it("'Entrar' takes the visitor to the seed login", () => {
    renderAt("/");
    const entrar = screen.getByTestId("link-entrar");
    expect(entrar).toHaveAttribute("href", "/login");
    fireEvent.click(entrar);
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("links the sponsor out in a new tab, without leaking the opener", () => {
    renderAt("/");
    const sponsor = screen.getByTestId("link-one-sponsor");
    expect(sponsor).toHaveAttribute("href", "https://oneconsultoriaimobiliaria.com.br/");
    expect(sponsor).toHaveAttribute("target", "_blank");
    expect(sponsor).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByTestId("link-pilares")).toHaveAttribute("href", "#pilares");
  });

  it("restores the page's scroll behaviour when it unmounts", () => {
    document.documentElement.style.scrollBehavior = "";
    const { unmount } = renderAt("/");
    expect(document.documentElement.style.scrollBehavior).toBe("smooth");
    unmount();
    expect(document.documentElement.style.scrollBehavior).toBe("");
  });

  it("'O Projeto' nav link points to the /o-projeto page", () => {
    renderAt("/");
    expect(screen.getByTestId("link-projeto")).toHaveAttribute("href", "/o-projeto");
  });

  it("'Como funciona' is an in-page anchor on the landing, not a route", () => {
    renderAt("/");
    expect(screen.getByTestId("link-como-funciona")).toHaveAttribute("href", "#como-funciona");
  });

  it("'A Carta' nav link points to the new /a-carta page", () => {
    renderAt("/");
    expect(screen.getByTestId("link-a-carta")).toHaveAttribute("href", "/a-carta");
  });

  it("gives the 30-toneladas infographic its own section, with the sourced numbers", () => {
    renderAt("/");
    // The image the reading pages used to interleave now lives here.
    expect(screen.getByTestId("infografico-30-toneladas")).toBeInTheDocument();
    expect(screen.getByTestId("tonnage-toneladas")).toHaveTextContent("+30 t");
    expect(screen.getByTestId("tonnage-conteineres")).toHaveTextContent("+70");
    expect(screen.getByTestId("tonnage-municipios")).toHaveTextContent("4");
    expect(screen.getByTestId("link-tonnage-projeto")).toHaveAttribute("href", "/o-projeto");
  });

  it("'Ver o projeto' hero button points to the /o-projeto page", () => {
    renderAt("/");
    expect(screen.getByTestId("button-ver-metodo")).toHaveAttribute("href", "/o-projeto");
  });
});

describe("Landing — interest popup", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    mockCreateInteressado.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function openPopup() {
    const result = renderAt("/");
    act(() => {
      vi.advanceTimersByTime(POPUP_DELAY_MS);
    });
    return result;
  }

  it("does not show immediately on mount", () => {
    renderAt("/");
    expect(screen.queryByTestId("form-interessado")).not.toBeInTheDocument();
  });

  it("shows after a short delay", () => {
    openPopup();
    expect(screen.getByTestId("form-interessado")).toBeInTheDocument();
  });

  it("'X' dismisses it and suppresses it on the next mount", () => {
    const { unmount } = openPopup();
    fireEvent.click(screen.getByTestId("button-popup-close"));
    expect(screen.queryByTestId("form-interessado")).not.toBeInTheDocument();
    unmount();

    openPopup();
    expect(screen.queryByTestId("form-interessado")).not.toBeInTheDocument();
  });

  it("'Agora não' dismisses it and suppresses it on the next mount", () => {
    const { unmount } = openPopup();
    fireEvent.click(screen.getByTestId("button-popup-later"));
    expect(screen.queryByTestId("form-interessado")).not.toBeInTheDocument();
    unmount();

    openPopup();
    expect(screen.queryByTestId("form-interessado")).not.toBeInTheDocument();
  });

  it("still shows when localStorage throws (private mode / quota) instead of crashing", () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() => openPopup()).not.toThrow();
    expect(screen.getByTestId("form-interessado")).toBeInTheDocument();
    getItemSpy.mockRestore();
  });

  it("submits the happy path, shows success, and suppresses the popup permanently", async () => {
    mockCreateInteressado.mockResolvedValue({ ok: true });
    openPopup();
    vi.useRealTimers();

    fireEvent.change(screen.getByTestId("input-nome"), { target: { value: "Maria Silva" } });
    fireEvent.change(screen.getByTestId("input-whatsapp"), { target: { value: "(11) 98765-4321" } });
    fireEvent.change(screen.getByTestId("input-email"), { target: { value: "maria@exemplo.com" } });
    fireEvent.click(screen.getByTestId("button-popup-submit"));

    await waitFor(() => expect(screen.getByTestId("popup-success")).toBeInTheDocument());
    expect(mockCreateInteressado).toHaveBeenCalledWith({
      nome: "Maria Silva",
      whatsapp: "(11) 98765-4321",
      email: "maria@exemplo.com",
      consentimento: true,
      origem: "/",
    });

    // Permanent suppression is recorded immediately on success — the next
    // mount's `shouldShowOnMount()` reads this and never shows it again.
    expect(JSON.parse(window.localStorage.getItem("academia:interessados-popup") ?? "{}")).toEqual({
      submitted: true,
    });
  });

  it("shows a 422 field error from the backend next to the offending field", async () => {
    mockCreateInteressado.mockRejectedValue(
      new ApiError(422, "Este e-mail já está em uso por outro contato.", {
        detail: "Este e-mail já está em uso por outro contato.",
        code: "invalid",
        field: "email",
      }),
    );
    openPopup();
    vi.useRealTimers();

    fireEvent.change(screen.getByTestId("input-nome"), { target: { value: "Maria Silva" } });
    fireEvent.change(screen.getByTestId("input-whatsapp"), { target: { value: "(11) 98765-4321" } });
    fireEvent.change(screen.getByTestId("input-email"), { target: { value: "maria@exemplo.com" } });
    fireEvent.click(screen.getByTestId("button-popup-submit"));

    await waitFor(() =>
      expect(screen.getByText("Este e-mail já está em uso por outro contato.")).toBeInTheDocument(),
    );
    // The popup is still open/usable — a 422 does not suppress it.
    expect(screen.getByTestId("form-interessado")).toBeInTheDocument();
  });
});
