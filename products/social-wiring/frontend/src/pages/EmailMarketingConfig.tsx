/**
 * EmailMarketingConfig — Mailchimp API key setup and audience picker.
 *
 * States:
 *   1. Not connected → API key form (password input) → on PUT success →
 *      audience picker + success banner.
 *   2. Connected → masked status + audience select + Substituir chave +
 *      Desconectar.
 *
 * This page is intentionally NOT wrapped in <MailchimpGate> — it IS the
 * gate configuration page. Disconnected → show the key form.
 */
import { useState } from "react";
import {
  Settings2,
  Key,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useMailchimpConnection,
  useMailchimpAudiences,
  useMailchimpConnectionMutations,
} from "@/hooks/useMailchimpConnection";

export default function EmailMarketingConfig() {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this whole config page on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data: connection, isPending } = useMailchimpConnection();
  const { put, patch, remove } = useMailchimpConnectionMutations();
  const { data: audiences } = useMailchimpAudiences(connection?.connected === true);

  const [apiKey, setApiKey] = useState("");
  const [putError, setPutError] = useState<string | null>(null);
  const [showReplaceForm, setShowReplaceForm] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setPutError(null);
    put.mutate(
      { api_key: apiKey },
      {
        onSuccess: () => {
          toast.success("Mailchimp conectado com sucesso!");
          setApiKey("");
        },
        onError: (err: unknown) => {
          // api client throws Error("[<status>] <message>") on non-2xx.
          // Strip the leading "[400] " prefix to show a clean message.
          const raw = (err as Error)?.message ?? "";
          const detail = raw.replace(/^\[\d+\]\s*/, "") || "Chave inválida ou formato incorreto.";
          setPutError(detail);
        },
      },
    );
  }

  function handleAudienceChange(audienceId: string) {
    patch.mutate(
      { audience_id: audienceId },
      {
        onSuccess: () => toast.success("Audiência padrão atualizada."),
        onError: () => toast.error("Erro ao atualizar audiência."),
      },
    );
  }

  function handleDisconnect() {
    remove.mutate(undefined, {
      onSuccess: () => {
        toast.success("Mailchimp desconectado.");
        setShowDeleteDialog(false);
        setShowReplaceForm(false);
      },
      onError: () => toast.error("Erro ao desconectar."),
    });
  }

  if (isPending) {
    return (
      <div className="p-6 max-w-2xl mx-auto space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const connected = connection?.connected === true;

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Settings2 className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold">Configuração do Mailchimp</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie a integração com sua conta Mailchimp.
          </p>
        </div>
      </div>

      {/* ─── Not connected — API key form ─────────────────────────────── */}
      {(!connected || showReplaceForm) && (
        <Card data-testid="mailchimp-config-form">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              {showReplaceForm ? "Substituir chave API" : "Conectar Mailchimp"}
            </CardTitle>
            <CardDescription>
              Encontre sua chave em{" "}
              <strong>Account → Extras → API keys</strong>. Formato esperado:{" "}
              <code className="text-xs bg-muted px-1 rounded">xxxx-us6</code>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleConnect} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="api-key">Chave API Mailchimp</Label>
                <Input
                  id="api-key"
                  data-testid="mailchimp-api-key-input"
                  type="password"
                  placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-us6"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setPutError(null);
                  }}
                  disabled={put.isPending}
                  autoComplete="off"
                />
              </div>

              {putError && (
                <div
                  className="flex items-center gap-2 text-sm text-destructive"
                  data-testid="mailchimp-connect-error"
                >
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {putError}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  type="submit"
                  disabled={!apiKey.trim() || put.isPending}
                  data-testid="mailchimp-connect-submit"
                >
                  {put.isPending ? "Conectando..." : "Conectar"}
                </Button>
                {showReplaceForm && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setShowReplaceForm(false);
                      setApiKey("");
                      setPutError(null);
                    }}
                  >
                    Cancelar
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* ─── Connected state ──────────────────────────────────────────── */}
      {connected && !showReplaceForm && (
        <>
          <Card data-testid="mailchimp-connected-state">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
                Mailchimp conectado
              </CardTitle>
              <CardDescription>
                Servidor:{" "}
                <span className="font-medium">{connection.server_prefix ?? "—"}</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Audience picker */}
              <div className="space-y-1.5">
                <Label htmlFor="audience-select">Audiência padrão</Label>
                {audiences ? (
                  <Select
                    value={connection.audience_id ?? ""}
                    onValueChange={handleAudienceChange}
                    disabled={patch.isPending}
                  >
                    <SelectTrigger
                      id="audience-select"
                      data-testid="mailchimp-audience-select"
                    >
                      <SelectValue placeholder="Selecione uma audiência" />
                    </SelectTrigger>
                    <SelectContent>
                      {audiences.items.map((a) => (
                        <SelectItem key={a.id} value={a.id}>
                          {a.name} ({a.member_count} membros)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Skeleton className="h-10 w-full" />
                )}
              </div>

              <div className="flex gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => setShowReplaceForm(true)}
                  data-testid="mailchimp-replace-key-btn"
                >
                  <RefreshCw className="h-4 w-4" />
                  Substituir chave
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  className="gap-2"
                  onClick={() => setShowDeleteDialog(true)}
                  data-testid="mailchimp-disconnect-btn"
                >
                  <Trash2 className="h-4 w-4" />
                  Desconectar
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* ─── Disconnect confirm ───────────────────────────────────────── */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desconectar Mailchimp?</AlertDialogTitle>
            <AlertDialogDescription>
              A chave API armazenada será removida. Contatos, listas, templates
              e campanhas permanecem na sua conta Mailchimp.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDisconnect}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="mailchimp-confirm-disconnect"
            >
              {remove.isPending ? "Desconectando..." : "Desconectar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
