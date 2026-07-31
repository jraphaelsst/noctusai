/**
 * WhatsApp — the unified WhatsApp (WAHA) surface at /whatsapp-chat.
 *
 * Remodel of the pre-Wave-5 bespoke 2-pane chat page into a YouTube/Meta-style
 * shell (see `pages/YouTube.tsx` / `pages/MetaDashboard.tsx`): a connection
 * selector in the header + two subtabs, so WhatsApp joins the unified
 * SocialDashboardShell pattern (the N=3 that formalizes the recurrence rule
 * for `@noctusai/lib/design-system`'s `SocialDashboardShell` + `ChatWindow`).
 *
 *   Chat           — the connection's live conversations, rendered via the
 *                     shared seed `<ChatWindow>` organ through the existing
 *                     `WhatsAppChatWindow` adapter (`components/WhatsAppChatWindow.tsx`
 *                     — reused verbatim, not re-wrapped: this file never talks
 *                     to `useWhatsAppChats`/`useSendWhatsAppMessage`/etc directly).
 *   Configurações  — QR pairing / session actions / auto-reply / editable
 *                     fields / authorized numbers / bound chats for the
 *                     selected connection, via `ConnectionSettingsPanel`
 *                     (`components/ConnectionDetailDialog.tsx` — the same
 *                     WAHA management body the ClienteModal/Conexoes modal
 *                     uses, extracted so it also renders inline here).
 *
 * Connection selection lives at the page level (the `accountSwitcher` shell
 * slot) so both subtabs read the SAME selected connection. Deep-links from a
 * connected WhatsApp `IntegrationCard` (`ClienteModal`'s card-body click, or
 * `Conexoes`'s) pre-select the connection via the shared
 * `useActiveAccountStore` — the same store YouTube/Meta already use for their
 * account switchers, here holding a WAHA `connection.id` instead of an
 * `integration_accounts.id` (WhatsApp connections aren't rows in that table).
 */
import { useEffect, useState } from "react";
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

import { WhatsAppChatWindow } from "@/components/WhatsAppChatWindow";
import { ConnectionSettingsPanel } from "@/components/ConnectionDetailDialog";
import {
  useWhatsAppConnections,
  useWhatsAppConnectionMutations,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import { useActiveAccountId } from "@/state/useActiveAccount";

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

// ─── Chat subtab ──────────────────────────────────────────────────────────────

function ChatPanel({ connection }: { connection: WhatsAppConnectionLine | null }) {
  if (!connection) return <NoConnectionsState />;
  return (
    <WhatsAppChatWindow
      connectionId={connection.id}
      autoReplyEnabled={connection.auto_reply_enabled}
      className="h-[calc(100vh-18rem)] min-h-[28rem] rounded-md border"
    />
  );
}

// ─── Configurações subtab ─────────────────────────────────────────────────────

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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WhatsAppChat() {
  const { data: connections = [], isLoading, isError } = useWhatsAppConnections();
  const { remove } = useWhatsAppConnectionMutations();

  const activeAccountId = useActiveAccountId("whatsapp");

  const [selectedConnId, setSelectedConnId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WhatsAppConnectionLine | null>(null);

  // Default-select on load: prefer a deep-linked connection (from
  // useActiveAccountStore — set by a connected-card body click), else keep
  // the current selection if still valid, else fall back to the first
  // connection. Mirrors the pre-Wave-5 page's "default first connection"
  // behaviour, extended with the deep-link pre-selection.
  useEffect(() => {
    if (connections.length === 0) {
      if (selectedConnId !== null) setSelectedConnId(null);
      return;
    }
    if (selectedConnId && connections.some((c) => c.id === selectedConnId)) {
      return;
    }
    const preferred =
      activeAccountId && connections.some((c) => c.id === activeAccountId)
        ? activeAccountId
        : connections[0].id;
    setSelectedConnId(preferred);
  }, [connections, activeAccountId, selectedConnId]);

  const selectedConn =
    connections.find((c) => c.id === selectedConnId) ?? null;

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

  if (isLoading) {
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

  const SUBTABS: SocialDashboardSubtab[] = [
    {
      key: "chat",
      label: "Chat",
      icon: MessageCircle,
      render: () => <ChatPanel connection={selectedConn} />,
    },
    {
      key: "config",
      label: "Configurações",
      icon: SettingsIcon,
      render: () => (
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
        title="WhatsApp"
        subtitle="Conversas e configuração das suas conexões WhatsApp (WAHA)."
        accountSwitcher={
          <WhatsAppConnectionSelector
            connections={connections}
            selectedId={selectedConnId}
            onChange={setSelectedConnId}
          />
        }
        subtabs={SUBTABS}
        defaultSubtab="chat"
      />

      {/* Delete confirm — mirrors the Conexoes/ClienteModal pattern */}
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
