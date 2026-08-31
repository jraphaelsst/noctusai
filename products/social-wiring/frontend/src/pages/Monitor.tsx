/**
 * Monitor page — live window into WhatsApp intake conversations.
 *
 *   Left   conversation list (auto-polling), non-idle surfaced on top
 *   Right  selected conversation: state + recent message history,
 *          plus a "cancel stuck flow" action (clears transient Redis
 *          state only; the user can re-send immediately)
 *
 * Data + mutation come from the seed intake hooks; presentation only.
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  Loader2,
  MessageSquare,
  RefreshCw,
  XCircle,
  Inbox,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import {
  useIntakeConversations,
  useIntakeConversation,
  useCancelConversation,
  type IntakeConversation,
} from "@/hooks/useWhatsAppIntake";

const STATE_LABELS: Record<string, string> = {
  idle: "Ocioso",
  awaiting_confirmation: "Aguardando confirmação",
  awaiting_manual_title: "Aguardando título",
  awaiting_video_choice: "Aguardando escolha de vídeo",
  processing: "Processando",
};

function StateBadge({ state }: { state: string }) {
  const variant =
    state === "processing"
      ? "default"
      : state === "idle"
        ? "secondary"
        : "outline";
  return (
    <Badge variant={variant as any} className="whitespace-nowrap">
      {STATE_LABELS[state] ?? state}
    </Badge>
  );
}

function ConversationRow({
  c,
  active,
  onClick,
}: {
  c: IntakeConversation;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full flex-col gap-1 border-b px-3 py-3 text-left last:border-0 hover:bg-muted/40 ${
        active ? "bg-muted/60" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-sm">{c.session_id}</span>
        <StateBadge state={c.state} />
      </div>
      <div className="flex items-center gap-2 truncate text-xs text-muted-foreground">
        {c.product_code && (
          <Badge variant="outline" className="text-[10px] font-mono">
            {c.product_code}
          </Badge>
        )}
        {c.video_filename && <span className="truncate">{c.video_filename}</span>}
        {c.active_uploads > 0 && (
          <span className="text-amber-600">
            {c.active_uploads} upload(s) ativo(s)
          </span>
        )}
      </div>
    </button>
  );
}

function DetailPanel({ sessionId }: { sessionId: string }) {
  // NOT `isLoading` — banned per KB § PATTERNS/frontend/lying-loading-state.md.
  // `!data` alone already IS the correct "nothing to render yet" signal
  // (undefined until first resolve, then persists); this endpoint also
  // polls every 5s, so a bare `isFetching` here would have re-blanked the
  // detail panel on every poll tick — `!data` never does.
  const { data } = useIntakeConversation(sessionId);
  const cancel = useCancelConversation();

  const onCancel = () =>
    cancel.mutate(sessionId, {
      onSuccess: (r) =>
        toast.success(
          r.cleared ? "Fluxo cancelado" : "Nada para cancelar",
        ),
      onError: (e: any) =>
        toast.error(e?.message ?? "Falha ao cancelar"),
    });

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const { conversation: c, messages } = data;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <div className="font-mono text-sm">{c.session_id}</div>
          <StateBadge state={c.state} />
        </div>
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {c.product_code && (
            <div>
              Código: <span className="font-mono">{c.product_code}</span>
            </div>
          )}
          {c.video_format && <div>Formato: {c.video_format}</div>}
          {c.video_filename && (
            <div className="col-span-2 truncate">
              Arquivo: {c.video_filename}
            </div>
          )}
          {c.drive_url && (
            <div className="col-span-2 truncate">
              Drive:{" "}
              <a
                href={c.drive_url}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                {c.drive_url}
              </a>
            </div>
          )}
        </div>
        <div className="mt-3">
          <Button
            variant="destructive"
            size="sm"
            onClick={onCancel}
            disabled={cancel.isPending || c.state === "idle"}
          >
            {cancel.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <XCircle className="mr-2 h-4 w-4" />
            )}
            Cancelar fluxo
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
            <MessageSquare className="h-6 w-6" />
            Sem histórico de mensagens
          </div>
        ) : (
          <div className="space-y-2">
            {messages.map((m, i) => (
              <div
                key={m.provider_message_id ?? i}
                className={`flex ${
                  m.direction === "outbound" ? "justify-start" : "justify-end"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    m.direction === "outbound"
                      ? "bg-muted"
                      : "bg-primary text-primary-foreground"
                  }`}
                >
                  <div className="whitespace-pre-wrap break-words">
                    {m.body}
                  </div>
                  {m.created_at && (
                    <div className="mt-1 text-[10px] opacity-60">
                      {new Date(m.created_at).toLocaleString("pt-BR")}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function MonitorPage() {
  // `isPending`, not `isLoading` — same polling reasoning as above: this
  // list also refetches every 5s, so the gate below must stay FALSE
  // after the first successful load, never re-fire on a poll tick.
  const { data: conversations, isPending, refetch } = useIntakeConversations();
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Monitor de fluxo</h1>
          <p className="text-sm text-muted-foreground">
            Conversas de WhatsApp ativas, seus estados e histórico — em
            tempo real.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Atualizar
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="grid min-h-[28rem] grid-cols-1 md:grid-cols-[20rem_1fr]">
          <div className="border-r">
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Conversas</CardTitle>
              <CardDescription className="text-xs">
                Estados que precisam de atenção aparecem no topo
              </CardDescription>
            </CardHeader>
            <Separator />
            {isPending ? (
              <div className="flex items-center justify-center p-10">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : !conversations || conversations.length === 0 ? (
              <div className="flex flex-col items-center gap-2 p-10 text-center text-sm text-muted-foreground">
                <Inbox className="h-7 w-7" />
                Nenhuma conversa ativa
              </div>
            ) : (
              <div className="h-[28rem] overflow-y-auto">
                {conversations.map((c) => (
                  <ConversationRow
                    key={c.session_id}
                    c={c}
                    active={selected === c.session_id}
                    onClick={() => setSelected(c.session_id)}
                  />
                ))}
              </div>
            )}
          </div>
          <div>
            {selected ? (
              <DetailPanel sessionId={selected} />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-10 text-center text-sm text-muted-foreground">
                <AlertCircle className="h-7 w-7" />
                Selecione uma conversa para ver detalhes e histórico
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
