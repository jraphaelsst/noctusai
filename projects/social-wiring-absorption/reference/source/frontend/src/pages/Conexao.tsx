/**
 * Conexao page — manage the WhatsApp (WAHA) connection without curl or
 * the WAHA dashboard.
 *
 *   Status card     live session state + linked account
 *   QR card         scan-to-pair (polls until linked) when unpaired
 *   Webhook card    one-click wire of the inbound webhook
 *   Danger zone     restart session / unlink account
 *
 * All data + mutations come from the seed `whatsapp_admin` router via the
 * seed hook factory; this page is presentation only.
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  CircleAlert,
  Loader2,
  Power,
  QrCode,
  RefreshCw,
  Link as LinkIcon,
  Smartphone,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import {
  useWhatsAppConnection,
  useWhatsAppQr,
  useWhatsAppActions,
} from "@/hooks/useWhatsAppConnection";

// Docker-internal URL WAHA uses to reach this backend (waha and app share
// the compose network). Pre-filled but editable for non-Docker deploys.
const DEFAULT_WEBHOOK_URL = "http://app:8010/api/whatsapp/webhook";

function StatusBadge({ status, paired }: { status: string | null; paired: boolean }) {
  if (paired) {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        {status ?? "WORKING"}
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <CircleAlert className="h-3 w-3" />
      {status ?? "desconectado"}
    </Badge>
  );
}

export default function ConexaoPage() {
  const { data: conn, isLoading } = useWhatsAppConnection();
  const paired = !!conn?.paired;
  const { data: qr } = useWhatsAppQr(!isLoading && !paired);
  const { useRestart, useLogout, useConfigureWebhook } = useWhatsAppActions();
  const restart = useRestart();
  const logout = useLogout();
  const configureWebhook = useConfigureWebhook();

  const [webhookUrl, setWebhookUrl] = useState(DEFAULT_WEBHOOK_URL);

  const onRestart = () =>
    restart.mutate(undefined, {
      onSuccess: () => toast.success("Sessão reiniciada"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao reiniciar"),
    });

  const onLogout = () =>
    logout.mutate(undefined, {
      onSuccess: () => toast.success("Conta desvinculada"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao desvincular"),
    });

  const onConfigureWebhook = () =>
    configureWebhook.mutate(
      { url: webhookUrl.trim() },
      {
        onSuccess: (r) =>
          toast.success(`Webhook configurado (${r.events.length} eventos)`),
        onError: (e: any) =>
          toast.error(e?.message ?? "Falha ao configurar webhook"),
      },
    );

  return (
    <div className="container max-w-3xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Conexão WhatsApp</h1>
        <p className="text-sm text-muted-foreground">
          Pareie o número, conecte o webhook e gerencie a sessão — sem
          terminal nem painel do WAHA.
        </p>
      </div>

      {/* Status */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="h-5 w-5" />
              Status da sessão
            </CardTitle>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : (
              <StatusBadge status={conn?.status ?? null} paired={paired} />
            )}
          </div>
          <CardDescription>
            Sessão <code className="font-mono">{conn?.session ?? "default"}</code>
            {conn && !conn.configured && " · modo não configurado (sem WAHA_BASE_URL)"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {paired ? (
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <span>
                Conectado como{" "}
                <strong>{conn?.me_name ?? conn?.me_id ?? "—"}</strong>
                {conn?.me_id && (
                  <span className="text-muted-foreground"> ({conn.me_id})</span>
                )}
              </span>
            </div>
          ) : (
            <p className="text-muted-foreground">
              Nenhuma conta vinculada. Escaneie o QR abaixo para parear.
            </p>
          )}
          {conn?.error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive">
              {conn.error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* QR pairing — only while unpaired */}
      {!paired && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5" />
              Parear número
            </CardTitle>
            <CardDescription>
              No WhatsApp do número: Aparelhos conectados → Conectar
              aparelho → escaneie. A página atualiza sozinha ao conectar.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center gap-3">
            {qr?.scannable && qr.png_base64 ? (
              <img
                src={`data:image/png;base64,${qr.png_base64}`}
                alt="QR code para parear o WhatsApp"
                className="h-64 w-64 rounded-md border bg-white p-2"
              />
            ) : (
              <div className="flex h-64 w-64 flex-col items-center justify-center gap-2 rounded-md border border-dashed text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                {qr?.status
                  ? `Aguardando QR (status: ${qr.status})`
                  : "Gerando QR..."}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Webhook wiring */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LinkIcon className="h-5 w-5" />
            Webhook de entrada
          </CardTitle>
          <CardDescription>
            URL que o WAHA chama a cada mensagem recebida. Padrão = endereço
            interno do Docker (rede compartilhada waha ↔ app).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="webhook-url">URL do webhook</Label>
            <Input
              id="webhook-url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder={DEFAULT_WEBHOOK_URL}
            />
          </div>
          <Button
            onClick={onConfigureWebhook}
            disabled={configureWebhook.isPending || !webhookUrl.trim()}
          >
            {configureWebhook.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <LinkIcon className="mr-2 h-4 w-4" />
            )}
            Configurar webhook
          </Button>
        </CardContent>
      </Card>

      {/* Danger zone */}
      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="text-base">Sessão</CardTitle>
          <CardDescription>
            Reiniciar recupera uma sessão travada (mantém o pareamento se as
            credenciais ainda forem válidas). Desvincular remove a conta.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={onRestart}
            disabled={restart.isPending}
          >
            {restart.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Reiniciar sessão
          </Button>
          <Separator orientation="vertical" className="h-9" />
          <Button
            variant="destructive"
            onClick={onLogout}
            disabled={logout.isPending || !paired}
          >
            {logout.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Power className="mr-2 h-4 w-4" />
            )}
            Desvincular conta
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
