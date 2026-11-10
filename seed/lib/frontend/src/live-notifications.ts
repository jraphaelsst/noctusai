/**
 * Live notifications: turn a NEW backend notice into a neutral operational pop-up.
 *
 * Reads the SAME list the bell shows (`hooks.useNotificacoes(1, 10)`, which refetches when the unread count moves (the bell polls ONE count every 60 s) while the tab is
 * visible and on focus), so there is one request, not two. Pure selection lives in
 * {@link selectFreshNotifications} so the rules are testable without React:
 *   - the first successful load of a session NEVER toasts (it only sets the high-water mark);
 *   - only unread notices created at/after the mark and not shown before toast;
 *   - at most {@link MAX_LIVE_TOASTS} at once, the rest collapse into "+N novas notificações".
 */
import { useEffect, useRef } from "react";
import { toastOperacional } from "./operational-toast";
import { notificationLink, notificationProduct, withNextPath } from "./design-system/components/NotificationBell";
import type { NotificationHooks } from "./design-system/components/NotificationBell";
import type { Notificacao } from "./notifications";

export const MAX_LIVE_TOASTS = 3;

export interface LiveState {
  /** False until the first successful load has been absorbed (that load never toasts). */
  initialized: boolean;
  /** Newest `created_at` (epoch ms) already accounted for. */
  highWater: number;
  seen: Set<string>;
}

export function newLiveState(): LiveState {
  return { initialized: false, highWater: 0, seen: new Set() };
}

const ts = (n: Pick<Notificacao, "created_at">) => {
  const t = Date.parse(n.created_at);
  return Number.isNaN(t) ? 0 : t;
};

/**
 * Absorb a fetched list and return the notices that deserve a pop-up (oldest first). Mutates `state`.
 * The first call only initializes (returns []): the backlog is what the bell is for.
 */
export function selectFreshNotifications(items: Notificacao[], state: LiveState): Notificacao[] {
  const newest = items.reduce((m, n) => Math.max(m, ts(n)), 0);
  if (!state.initialized) {
    state.initialized = true;
    state.highWater = newest;
    items.forEach((n) => state.seen.add(n.id));
    return [];
  }
  const fresh = items
    .filter((n) => !n.is_read && !state.seen.has(n.id) && ts(n) >= state.highWater)
    .sort((a, b) => ts(a) - ts(b));
  items.forEach((n) => state.seen.add(n.id));
  state.highWater = Math.max(state.highWater, newest);
  return fresh;
}

export interface LiveNotificationsOptions {
  hooks: NotificationHooks;
  /** react-router `navigate`: opens an in-app link of this product. */
  onNavigate?: (link: string) => void;
  currentProduct?: string;
  onNavigateProduct?: (product: string, link: string) => void | Promise<void>;
}

/** Mount ONCE per authenticated shell. Renders nothing; pops neutral toasts for new notices. */
export function useLiveNotifications({ hooks, onNavigate, currentProduct, onNavigateProduct }: LiveNotificationsOptions): void {
  const { data } = hooks.useNotificacoes(1, 10);
  const marcarLida = hooks.useMarcarComoLida();
  const state = useRef<LiveState>(newLiveState());
  const latest = useRef({ onNavigate, currentProduct, onNavigateProduct, marcar: marcarLida.mutate });
  latest.current = { onNavigate, currentProduct, onNavigateProduct, marcar: marcarLida.mutate };
  const pending = useRef<Notificacao[] | undefined>(undefined);

  const flush = useRef(() => {
    const items = pending.current;
    if (!items) return;
    // A hidden tab keeps its list for when it is visible again; the mark only advances on a real flush.
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    pending.current = undefined;
    const fresh = selectFreshNotifications(items, state.current);
    fresh.slice(0, MAX_LIVE_TOASTS).forEach((n) => {
      const link = notificationLink(n);
      toastOperacional({
        id: `notificacao-${n.id}`,
        title: n.titulo,
        message: n.mensagem,
        link,
        onOpen: () => {
          const ctx = latest.current;
          if (!n.is_read) ctx.marcar(n.id);
          if (!link) return;
          const produto = notificationProduct(n);
          if (produto && produto !== (ctx.currentProduct ?? "")) {
            if (ctx.onNavigateProduct) {
              try { void Promise.resolve(ctx.onNavigateProduct(produto, link)).catch(() => undefined); } catch { /* refused: read, no navigation */ }
            }
          } else {
            ctx.onNavigate?.(link);
          }
        },
      });
    });
    const resto = fresh.length - MAX_LIVE_TOASTS;
    if (resto > 0) {
      toastOperacional({ id: "notificacoes-resumo", title: `+${resto} novas notificações`, message: "Abra o sino para ver todas." });
    }
  });

  useEffect(() => {
    if (!data?.data) return;
    pending.current = data.data;
    flush.current();
  }, [data]);

  useEffect(() => {
    const onVisible = () => flush.current();
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);
}

/**
 * Build the "open this link inside ANOTHER product" navigator from core's launch-URL minter: `requestLaunchUrl(product)`
 * must return the SSO `redirect_url` (core: POST /api/sso/token, which also checks licence + known product). Rejects
 * on refusal, so a caller navigates nowhere. One implementation for every product's bell AND pop-up.
 */
export function createOpenInProduct(
  requestLaunchUrl: (product: string) => Promise<string>,
  assign: (url: string) => void = (u) => window.location.assign(u),
) {
  return async function openInProduct(product: string, link: string): Promise<void> {
    const target = withNextPath(await requestLaunchUrl(product), link);
    if (!target) throw new Error("launch url refused");
    assign(target);
  };
}
