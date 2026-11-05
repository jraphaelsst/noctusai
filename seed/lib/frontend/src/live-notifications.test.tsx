/** Live notifications: high-water mark, cap, visibility, link routing. */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toastOperacional = vi.fn();
vi.mock("./operational-toast", () => ({ toastOperacional: (o: unknown) => toastOperacional(o) }));

import { MAX_LIVE_TOASTS, createOpenInProduct, newLiveState, selectFreshNotifications, useLiveNotifications } from "./live-notifications";
import type { Notificacao } from "./notifications";

let seq = 0;
const n = (over: Partial<Notificacao> = {}): Notificacao => {
  seq += 1;
  return { id: `n${seq}`, org_id: "o", user_id: "u", tipo: "lead_novo", titulo: `Aviso ${seq}`, is_read: false, created_at: new Date(1_700_000_000_000 + seq * 1000).toISOString(), ...over };
};

beforeEach(() => { seq = 0; toastOperacional.mockClear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("selectFreshNotifications", () => {
  it("never toasts the backlog on the first load", () => {
    const st = newLiveState();
    expect(selectFreshNotifications([n(), n(), n()], st)).toEqual([]);
    expect(st.initialized).toBe(true);
  });

  it("toasts only unread notices newer than the mark, once each", () => {
    const st = newLiveState();
    const old = [n(), n()];
    selectFreshNotifications(old, st);
    const novo = n();
    const lida = n({ is_read: true });
    expect(selectFreshNotifications([lida, novo, ...old], st).map((x) => x.id)).toEqual([novo.id]);
    // the same poll again: nothing new
    expect(selectFreshNotifications([lida, novo, ...old], st)).toEqual([]);
  });

  it("an empty first load still initializes (the next notice is fresh)", () => {
    const st = newLiveState();
    selectFreshNotifications([], st);
    const novo = n();
    expect(selectFreshNotifications([novo], st).map((x) => x.id)).toEqual([novo.id]);
  });
});

function setup(initial: Notificacao[]) {
  let items = initial;
  const marcar = vi.fn();
  const onNavigate = vi.fn();
  const onNavigateProduct = vi.fn();
  const hooks = {
    useNotificacoes: () => ({ data: { data: items } }),
    useContagemNaoLidas: () => ({ data: { nao_lidas: 0 } }),
    useMarcarComoLida: () => ({ mutate: marcar, isPending: false }),
    useMarcarTodasComoLidas: () => ({ mutate: vi.fn(), isPending: false }),
  };
  const view = renderHook(() => useLiveNotifications({ hooks, onNavigate, currentProduct: "social-wiring", onNavigateProduct }));
  const poll = (next: Notificacao[]) => { items = next; view.rerender(); };
  return { poll, marcar, onNavigate, onNavigateProduct };
}

describe("useLiveNotifications", () => {
  it("no toast on first load; one neutral toast per new notice", () => {
    const base = [n(), n()];
    const { poll } = setup(base);
    expect(toastOperacional).not.toHaveBeenCalled();
    const novo = n({ titulo: "Novo lead: Maria", mensagem: "Chegou agora" });
    poll([novo, ...base]);
    expect(toastOperacional).toHaveBeenCalledTimes(1);
    expect(toastOperacional.mock.calls[0][0]).toMatchObject({ title: "Novo lead: Maria", message: "Chegou agora" });
  });

  it(`caps at ${MAX_LIVE_TOASTS} and collapses the rest into "+N novas notificações"`, () => {
    const base = [n()];
    const { poll } = setup(base);
    const novos = [n(), n(), n(), n(), n()];
    poll([...novos, ...base]);
    const titles = toastOperacional.mock.calls.map((c) => (c[0] as { title: string }).title);
    expect(titles).toHaveLength(MAX_LIVE_TOASTS + 1);
    expect(titles[titles.length - 1]).toBe("+2 novas notificações");
  });

  it("does not toast while the tab is hidden; toasts when it becomes visible", () => {
    const vis = vi.spyOn(document, "visibilityState", "get");
    vis.mockReturnValue("visible");
    const base = [n()];
    const { poll } = setup(base);
    vis.mockReturnValue("hidden");
    poll([n(), ...base]);
    expect(toastOperacional).not.toHaveBeenCalled();
    vis.mockReturnValue("visible");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(toastOperacional).toHaveBeenCalledTimes(1);
  });

  it("click opens the in-app link and marks it read; cross-product goes through onNavigateProduct", () => {
    const base = [n()];
    const { poll, marcar, onNavigate, onNavigateProduct } = setup(base);
    const local = n({ metadata: { link: "/leads" } });
    const outro = n({ metadata: { link: "/imoveis", produto: "agents" } });
    poll([local, outro, ...base]);
    (toastOperacional.mock.calls[0][0] as { onOpen: () => void }).onOpen();
    expect(onNavigate).toHaveBeenCalledWith("/leads");
    expect(marcar).toHaveBeenCalledWith(local.id);
    (toastOperacional.mock.calls[1][0] as { onOpen: () => void }).onOpen();
    expect(onNavigateProduct).toHaveBeenCalledWith("agents", "/imoveis");
  });
});

describe("createOpenInProduct", () => {
  it("appends next=<link> to the minted launch URL and navigates", async () => {
    const assign = vi.fn();
    await createOpenInProduct(async () => "https://sw.example/sso#token=abc", assign)("social-wiring", "/leads");
    expect(assign).toHaveBeenCalledTimes(1);
    expect(assign.mock.calls[0][0]).toContain("next=%2Fleads");
  });
  it("rejects (navigates nowhere) when the launch URL is refused", async () => {
    const assign = vi.fn();
    await expect(createOpenInProduct(async () => "javascript:alert(1)", assign)("p", "/x")).rejects.toThrow();
    expect(assign).not.toHaveBeenCalled();
  });
});
