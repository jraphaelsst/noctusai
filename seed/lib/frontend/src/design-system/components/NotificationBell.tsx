/**
 * Shared NotificationBell component for all NoctusAI products.
 *
 * Self-contained (no shadcn dependencies) so it works across all products
 * regardless of which UI primitives they have installed.
 *
 * Usage:
 *   import { NotificationBell } from "@noctusai/lib/design-system";
 *   import { useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas } from "@/hooks/useNotificacoes";
 *
 *   <NotificationBell
 *     hooks={{ useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas }}
 *     viewAllPath="/notificacoes"  // optional
 *   />
 */
import { useState, useRef, useEffect, type ReactNode } from "react";
import { Bell, Check, CheckCheck, Clock } from "lucide-react";
import type { Notificacao } from "../../notifications";

// ── Types ──────────────────────────────────────────────────────────

interface PaginatedResponse {
  data: Notificacao[];
  pagination?: unknown;
}

interface MutationResult<TVariables = void> {
  mutate: (variables: TVariables) => void;
  isPending: boolean;
}

export interface NotificationHooks {
  useNotificacoes: (page?: number, pageSize?: number) => { data: PaginatedResponse | undefined };
  useContagemNaoLidas: () => { data: { nao_lidas: number } | undefined };
  useMarcarComoLida: () => MutationResult<string>;
  useMarcarTodasComoLidas: () => MutationResult<void>;
}

export interface NotificationBellProps {
  /** Hooks object returned by createNotificationHooks (or individual hooks) */
  hooks: NotificationHooks;
  /** Optional path for a "View all" link at the bottom of the dropdown */
  viewAllPath?: string;
  /** Optional navigate function (e.g. from react-router's useNavigate) for the "View all" link */
  onViewAll?: () => void;
  /** Optional extra content at the bottom of the dropdown */
  footer?: ReactNode;
  /**
   * Open the record a notification points at. When given, a notification that carries an in-app link
   * (`link`, else `metadata.link`; see {@link notificationLink}) is clickable: it is marked read and
   * `onNavigate(link)` is called (e.g. react-router's `navigate`).
   */
  onNavigate?: (link: string) => void;
  /** Slug of the product this bell is rendered in (`env.PRODUCT_SLUG`). Notices whose `metadata.product` differs are cross-product. */
  currentProduct?: string;
  /**
   * Open `link` (a validated path) inside ANOTHER product (full navigation, same tab). Called for a notice whose
   * `metadata.product` is a well-formed slug different from `currentProduct`. May reject (unknown product / no
   * access): the notice is still marked read, nothing navigates. Without it a cross-product notice is inert.
   */
  onNavigateProduct?: (product: string, link: string) => void | Promise<void>;
}

const PRODUCT_SLUG_RE = /^[a-z0-9][a-z0-9-]{0,62}$/;

/** The product a notice belongs to (`metadata.product`), only when it is a well-formed slug; else `null`. */
export function notificationProduct(n: Pick<Notificacao, "metadata">): string | null {
  const raw = n.metadata && typeof n.metadata === "object" ? (n.metadata as { product?: unknown }).product : null;
  return typeof raw === "string" && PRODUCT_SLUG_RE.test(raw) ? raw : null;
}

/**
 * Append a post-login landing path (`next`) to a core-built SSO launch URL. Path-only: a non-path `link` yields
 * `null` (the caller must not navigate). `next` rides the same component as the token (fragment for the strict
 * regime, query for the legacy one) and is consumed by `SSOCallback`.
 */
export function withNextPath(launchUrl: string, link: string): string | null {
  if (!link.startsWith("/") || link.startsWith("//")) return null;
  let u: URL;
  try { u = new URL(launchUrl); } catch { return null; }
  if (u.protocol !== "https:" && u.protocol !== "http:") return null;
  if (u.hash.includes("token=")) {
    const h = new URLSearchParams(u.hash.replace(/^#/, ""));
    h.set("next", link);
    u.hash = h.toString();
  } else {
    u.searchParams.set("next", link);
  }
  return u.toString();
}

/** The in-app path a notification opens, or `null`. Same-origin paths only ("/x", never "//host"). */
export function notificationLink(n: Pick<Notificacao, "link" | "metadata">): string | null {
  const meta = n.metadata && typeof n.metadata === "object" ? (n.metadata as { link?: unknown }).link : null;
  const raw = n.link ?? meta;
  return typeof raw === "string" && raw.startsWith("/") && !raw.startsWith("//") ? raw : null;
}

// ── Helpers ────────────────────────────────────────────────────────

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

// ── Component ──────────────────────────────────────────────────────

export function NotificationBell({ hooks, viewAllPath, onViewAll, footer, onNavigate, currentProduct, onNavigateProduct }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: notificacoesResp } = hooks.useNotificacoes(1, 10);
  const { data: contagem } = hooks.useContagemNaoLidas();
  const marcarLida = hooks.useMarcarComoLida();
  const marcarTodas = hooks.useMarcarTodasComoLidas();

  const notificacoes = notificacoesResp?.data || [];
  const naoLidas = contagem?.nao_lidas ?? 0;

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const showFooter = viewAllPath || onViewAll || footer;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-md hover:bg-accent transition-colors"
        aria-label="Notificacoes"
      >
        <Bell className="h-5 w-5" />
        {naoLidas > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-5 min-w-[20px] flex items-center justify-center bg-destructive text-destructive-foreground text-[10px] font-bold rounded-full px-1">
            {naoLidas > 99 ? "99+" : naoLidas}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-card border rounded-lg shadow-lg z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="text-sm font-semibold">Notificacoes</span>
            {naoLidas > 0 && (
              <button
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => marcarTodas.mutate()}
                disabled={marcarTodas.isPending}
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Marcar todas
              </button>
            )}
          </div>

          <div className="max-h-[320px] overflow-y-auto">
            {notificacoes.length === 0 ? (
              <div className="py-8 text-center">
                <Bell className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Nenhuma notificacao</p>
              </div>
            ) : (
              <div className="divide-y">
                {notificacoes.map((n) => {
                  const produto = notificationProduct(n);
                  const outro = !!produto && produto !== (currentProduct ?? "");
                  const rawLink = notificationLink(n);
                  const link = outro ? (onNavigateProduct ? rawLink : null) : onNavigate ? rawLink : null;
                  const abrir = () => {
                    if (!link) return;
                    if (!n.is_read) marcarLida.mutate(n.id);
                    setOpen(false);
                    if (outro && produto && onNavigateProduct) {
                      // Rejection (unknown product / no access) = no navigation; the notice is already read.
                      try {
                        void Promise.resolve(onNavigateProduct(produto, link)).catch(() => undefined);
                      } catch {
                        /* synchronous refusal: same outcome */
                      }
                    } else if (onNavigate) {
                      onNavigate(link);
                    }
                  };
                  return (
                  <div
                    key={n.id}
                    data-testid={`notificacao-${n.id}`}
                    role={link ? "link" : undefined}
                    tabIndex={link ? 0 : undefined}
                    onClick={link ? abrir : undefined}
                    onKeyDown={link ? (e) => { if (e.key === "Enter") abrir(); } : undefined}
                    className={`flex items-start gap-2.5 px-4 py-3 transition-colors ${
                      !n.is_read ? "bg-primary/5" : ""
                    } ${link ? "cursor-pointer hover:bg-accent" : ""}`}
                  >
                    <div
                      className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${
                        n.is_read ? "bg-transparent" : "bg-primary"
                      }`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-snug ${!n.is_read ? "font-medium" : ""}`}>
                        {n.titulo}
                      </p>
                      {outro && (
                        <span
                          data-testid={`notificacao-produto-${n.id}`}
                          className="inline-block mt-0.5 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                        >
                          {produto}
                        </span>
                      )}
                      {n.mensagem && (
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                          {n.mensagem}
                        </p>
                      )}
                      <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {timeAgo(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <button
                        className="p-1 rounded hover:bg-accent transition-colors shrink-0"
                        onClick={(e) => { e.stopPropagation(); marcarLida.mutate(n.id); }}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          {showFooter && (
            <div className="border-t px-4 py-2">
              {footer || (
                <button
                  className="w-full text-xs text-center py-1.5 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    if (onViewAll) onViewAll();
                    setOpen(false);
                  }}
                >
                  Ver todas as notificacoes
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
