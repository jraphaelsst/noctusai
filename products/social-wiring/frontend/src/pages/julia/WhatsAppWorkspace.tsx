/**
 * WhatsAppWorkspace — the shared layout behind the "Julia" WhatsApp (WAHA)
 * pages (owner decision 2026-10-13; formerly the single `/whatsapp-chat` page
 * with Chat + Configurações subtabs):
 *
 *   /julia/conversas     — `view="conversas"`: the connection's live
 *                          conversations via the existing `WhatsAppChatWindow`
 *                          adapter over the seed `<ChatWindow>` organ (reused
 *                          verbatim; this file never talks to
 *                          `useWhatsAppChats`/`useSendWhatsAppMessage` directly).
 *   /julia/configuracoes — `view="configuracoes"`: QR pairing / session actions /
 *                          auto-reply / fields / authorized numbers / bound chats
 *                          via `ConnectionSettingsPanel`
 *                          (`components/ConnectionDetailDialog.tsx` — the same
 *                          WAHA body the MarcaModal modal uses).
 *
 * ONE layout, one view per route — not two copies. Data loading, the
 * loading/error/empty states, the connection selector and the delete confirm
 * live here once; each route page is a one-line `<WhatsAppWorkspace view=…/>`.
 *
 * Connection selection is SHARED across both routes through
 * `useActiveAccountStore` (key `whatsapp`, persisted): picking a connection on
 * Conversas is still selected after navigating to Configurações, and a
 * connected WhatsApp `IntegrationCard` click (MarcaModal) writes the same key
 * before deep-linking, so it lands pre-selected. A WAHA `connection.id` is not
 * an `integration_accounts.id`, which is why it has its own provider key. No
 * valid stored id ⇒ the first connection.
 *
 * Rendered through the canonical `SocialDashboardShell` (`@noctusai/lib`) with
 * a single "WhatsApp" channel subtab — navigation between the views is the
 * sidebar's job (Julia group), not a second tab bar.
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  Loader2,
  MessageCircle,
  Settings as SettingsIcon,
  Smartphone,
  Trash2,
} from "lucide-react";

import {
  SocialDashboardShell,
  type SocialDashboardSubtab,
} from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";

import { ConversasPanel } from "@/components/julia/conversas/ConversasPanel";
import { ConnectionSettingsPanel } from "@/components/ConnectionDetailDialog";
import {
  useWhatsAppConnections,
  useWhatsAppConnectionMutations,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import {
  useActiveAccountId,
  useActiveAccountStore,
} from "@/state/useActiveAccount";
import { JULIA_LABEL, JULIA_PAGES } from "@/nav/julia";

// ─── Connection selector (accountSwitcher header slot) ───────────────────────
/**
 * Button-group connection picker — the pre-existing WA connection-picker
 * logic from the old page, lifted here so both subtabs share one selection.
 */
function WhatsAppConnectionSelector({
  connections,
  selectedId,
  onChange,
}: {
  connections: WhatsAppConnectionLine[];
  selectedId: string | null;
  onChange: (id: string) => void;
}) {
  return (
    <div
      className="flex items-center gap-2 overflow-x-auto"
      data-testid="wa-connection-selector"
    >
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        Conexão:
      </span>
      {connections.map((conn) => (
        <Button
          key={conn.id}
          variant={selectedId === conn.id ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(conn.id)}
          className="h-7 whitespace-nowrap text-xs"
        >
          {conn.label}
        </Button>
      ))}
    </div>
  );
}

// ─── Shared "no connection" empty state ──────────────────────────────────────

function NoConnectionsState() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-4 text-muted-foreground">
      <Smartphone className="h-12 w-12 opacity-30" />
      <div className="text-center">
        <p className="text-sm font-medium">Nenhuma conexão WhatsApp</p>
        <p className="mt-1 text-xs">
          Vá para{" "}
          <a href="/conexoes" className="text-primary underline">
            Conexões
          </a>{" "}
          para adicionar uma conexão.
        </p>
      </div>
    </div>
  );
}

// ─── Conversas view ──────────────────────────────────────────────────────────────

function ChatPanel({ connection }: { connection: WhatsAppConnectionLine | null }) {
  if (!connection) return <NoConnectionsState />;
  return (
    <ConversasPanel
      connectionId={connection.id}
      autoReplyEnabled={connection.auto_reply_enabled}
    />
  );
}

// ─── Configurações view ─────────────────────────────────────────────────────

function ConfigPanel({
  connection,
  onRequestDelete,
}: {
  connection: WhatsAppConnectionLine | null;
  onRequestDelete: (line: WhatsAppConnectionLine) => void;
}) {
  if (!connection) return <NoConnectionsState />;
  return (
    <div className="max-w-2xl rounded-md border bg-background p-6">
      <ConnectionSettingsPanel
        line={connection}
        onRequestDelete={onRequestDelete}
      />
    </div>
  );
}

// ─── Shared layout ────────────────────────────────────────────────────────────

/** The WhatsApp provider key in `useActiveAccountStore`. */
const WA_PROVIDER = "whatsapp";

export type WhatsAppWorkspaceView = "conversas" | "configuracoes";

const VIEW_META: Record<
  WhatsAppWorkspaceView,
  { subtitle: string; icon: typeof MessageCircle }
> = {
  conversas: {
    subtitle: "Conversas das suas conexões WhatsApp (WAHA).",
    icon: MessageCircle,
  },
  configuracoes: {
    subtitle: "Configuração das suas conexões WhatsApp (WAHA).",
    icon: SettingsIcon,
  },
};

export function WhatsAppWorkspace({ view }: { view: WhatsAppWorkspaceView }) {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this whole chat picker on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data: connections = [], isPending, isError } = useWhatsAppConnections();
  const { remove } = useWhatsAppConnectionMutations();

  // The selection IS the store entry — shared by both Julia routes and by the
  // IntegrationCard deep-link. A stale/foreign id falls back to the first
  // connection (derived, so there is no effect to race the first render).
  const activeAccountId = useActiveAccountId(WA_PROVIDER);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);
  const selectedConn =
    connections.find((c) => c.id === activeAccountId) ?? connections[0] ?? null;
  const selectConnection = (id: string) => setActiveAccount(WA_PROVIDER, id);

  const [deleteTarget, setDeleteTarget] = useState<WhatsAppConnectionLine | null>(null);

  function confirmDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Conexão excluída");
        setDeleteTarget(null);
      },
      onError: (e: unknown) =>
        toast.error(e instanceof Error ? e.message : "Falha ao excluir"),
    });
  }

  if (isPending) {
    return (
      <div className="flex h-64 items-center justify-center gap-3 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Carregando conexões...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-foreground">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm">Erro ao carregar conexões. Recarregue a página.</p>
      </div>
    );
  }

  if (connections.length === 0) {
    return (
      <div className="container max-w-7xl py-6">
        <NoConnectionsState />
      </div>
    );
  }

  const page = JULIA_PAGES[view];
  const SUBTABS: SocialDashboardSubtab[] = [
    {
      key: "whatsapp",
      label: "WhatsApp",
      icon: VIEW_META[view].icon,
      render: () =>
        view === "conversas" ? (
          <ChatPanel connection={selectedConn} />
        ) : (
          <ConfigPanel
            connection={selectedConn}
            onRequestDelete={setDeleteTarget}
          />
        ),
    },
  ];

  return (
    <>
      <SocialDashboardShell
        title={`${JULIA_LABEL} · ${page.name}`}
        subtitle={VIEW_META[view].subtitle}
        accountSwitcher={
          <WhatsAppConnectionSelector
            connections={connections}
            selectedId={selectedConn?.id ?? null}
            onChange={selectConnection}
          />
        }
        subtabs={SUBTABS}
        defaultSubtab="whatsapp"
      />

      {/* Delete confirm — mirrors the Conexoes/MarcaModal pattern */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={(e) => e.target === e.currentTarget && setDeleteTarget(null)}
        >
          <div className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h3 className="mb-2 flex items-center gap-2 font-semibold">
              <Trash2 className="h-4 w-4 text-destructive" />
              Excluir conexão?
            </h3>
            <p className="mb-6 text-sm text-muted-foreground">
              "{deleteTarget.label}" será removida permanentemente.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteTarget(null)}
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={confirmDelete}
                disabled={remove.isPending}
                data-testid="wa-confirm-delete"
              >
                {remove.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : null}
                Excluir
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
