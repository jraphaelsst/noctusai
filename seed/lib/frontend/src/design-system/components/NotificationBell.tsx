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

export function NotificationBell({ hooks, viewAllPath, onViewAll, footer }: NotificationBellProps) {
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
                {notificacoes.map((n) => (
                  <div
                    key={n.id}
                    className={`flex items-start gap-2.5 px-4 py-3 transition-colors ${
                      !n.is_read ? "bg-primary/5" : ""
                    }`}
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
                        onClick={() => marcarLida.mutate(n.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
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
