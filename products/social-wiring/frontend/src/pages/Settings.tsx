/**
 * Settings page — two-tab configuration cockpit.
 *
 *   Notifications tab    SMTP + WAHA status (read-only) + recipient CRUD
 *   API Keys tab         Read-only health badges from /api/settings/keys/status
 *
 * NOTE: The YouTube connection tab was removed — YouTube accounts are now
 * managed in the unified Conexoes page (/conexoes).
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  CircleAlert,
  Loader2,
  Plus,
  Trash2,
  Mail,
  MessageCircle,
  KeyRound,
} from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext, StatusPaginaPanel } from "@noctusai/lib";
import { api } from "@/lib/api";

import {
  useRecipients,
  useKeysStatus,
  useMetaAppStatus,
  useSaveMetaApp,
  useInstagramAppStatus,
  useSaveInstagramApp,
  type KeyStatusEntry,
  type Recipient,
  type RecipientCreate,
} from "@/hooks/useSettings";

// ─── Reusable bits ──────────────────────────────────────────────────────
function HealthBadge({ entry }: { entry: KeyStatusEntry }) {
  const ok = entry.health === "configured";
  return (
    <Badge
      variant={ok ? "default" : "destructive"}
      className="gap-1 font-mono text-[11px]"
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
      {ok ? "configurado" : "ausente"}
    </Badge>
  );
}

// ─── Notifications tab ──────────────────────────────────────────────────
const EMPTY_RECIPIENT: RecipientCreate = {
  name: "",
  email: "",
  whatsapp_number: "",
  is_active: true,
};

function NotificationsTab() {
  const { data, loading, create, update, remove } = useRecipients();
  const { data: keys } = useKeysStatus();
  const [draft, setDraft] = useState<RecipientCreate>(EMPTY_RECIPIENT);
  const [submitting, setSubmitting] = useState(false);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.name.trim()) {
      toast.error("Informe o nome do destinatario");
      return;
    }
    if (!draft.email && !draft.whatsapp_number) {
      toast.error("Informe pelo menos email ou whatsapp");
      return;
    }
    setSubmitting(true);
    try {
      await create({
        name: draft.name.trim(),
        email: draft.email || undefined,
        whatsapp_number: draft.whatsapp_number || undefined,
        is_active: draft.is_active,
      });
      setDraft(EMPTY_RECIPIENT);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Canais de notificacao</CardTitle>
          <CardDescription>
            Configurados via .env. Para alterar, edite os valores e reinicie o backend.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-md border p-4">
            <div className="mb-2 flex items-center gap-2">
              <Mail className="h-4 w-4" />
              <p className="font-medium">SMTP (email)</p>
              {keys && <HealthBadge entry={keys.smtp_user} />}
            </div>
            <p className="text-xs text-muted-foreground">
              {keys?.smtp_user.description}
            </p>
          </div>
          <div className="rounded-md border p-4">
            <div className="mb-2 flex items-center gap-2">
              <MessageCircle className="h-4 w-4" />
              <p className="font-medium">WAHA (WhatsApp)</p>
              {keys && <HealthBadge entry={keys.waha_base_url} />}
            </div>
            <p className="text-xs text-muted-foreground">
              {keys?.waha_base_url.description}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Destinatarios</CardTitle>
          <CardDescription>
            Lista fixa que recebe a notificacao em cada upload publicado.
            No momento do upload da para desmarcar individualmente.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleAdd}
            className="grid grid-cols-1 gap-3 sm:grid-cols-12"
          >
            <Input
              className="sm:col-span-3"
              placeholder="Nome"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
            <Input
              className="sm:col-span-3"
              type="email"
              placeholder="email@dominio.com"
              value={draft.email ?? ""}
              onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            />
            <Input
              className="sm:col-span-3"
              placeholder="+5511999999999"
              value={draft.whatsapp_number ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, whatsapp_number: e.target.value })
              }
            />
            <div className="flex items-center gap-2 sm:col-span-1">
              <Switch
                id="is-active"
                checked={!!draft.is_active}
                onCheckedChange={(v) => setDraft({ ...draft, is_active: v })}
              />
              <Label htmlFor="is-active" className="text-xs">
                ativo
              </Label>
            </div>
            <Button type="submit" className="sm:col-span-2" disabled={submitting}>
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Plus className="mr-2 h-4 w-4" /> Adicionar
                </>
              )}
            </Button>
          </form>

          <Separator className="my-6" />

          {loading ? (
            <div className="flex justify-center p-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : data.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum destinatario cadastrado ainda.
            </p>
          ) : (
            <div className="divide-y rounded-md border">
              {data.map((r) => (
                <RecipientRow
                  key={r.id}
                  recipient={r}
                  onToggleActive={(active) =>
                    update(r.id, { is_active: active })
                  }
                  onDelete={() => remove(r.id)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RecipientRow({
  recipient,
  onToggleActive,
  onDelete,
}: {
  recipient: Recipient;
  onToggleActive: (active: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="flex flex-1 flex-col">
        <p className="font-medium">{recipient.name}</p>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {recipient.email && <span>email: {recipient.email}</span>}
          {recipient.whatsapp_number && (
            <span>whatsapp: {recipient.whatsapp_number}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Switch
            checked={recipient.is_active}
            onCheckedChange={onToggleActive}
          />
          <span className="text-xs text-muted-foreground">
            {recipient.is_active ? "ativo" : "pausado"}
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onDelete}
          aria-label="Remover destinatario"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ─── API Keys tab ───────────────────────────────────────────────────────
function ApiKeysTab({ isAdminOrDev }: { isAdminOrDev: boolean }) {
  const { data, loading } = useKeysStatus();

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!data) {
    return (
      <p className="p-12 text-center text-sm text-muted-foreground">
        Nao foi possivel carregar o status das chaves.
      </p>
    );
  }

  const entries: [keyof typeof data, KeyStatusEntry][] = (
    Object.entries(data) as [keyof typeof data, KeyStatusEntry][]
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <KeyRound className="h-5 w-5 text-muted-foreground" />
            <div>
              <CardTitle>Chaves de API</CardTitle>
              <CardDescription>
                Status (somente leitura) das credenciais lidas do .env. Para
                alterar, edite o arquivo e reinicie o backend.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="divide-y rounded-md border">
            {entries.map(([key, entry]) => (
              <div
                key={key}
                className="flex items-start justify-between gap-4 px-4 py-3"
              >
                <div className="flex flex-1 flex-col">
                  <p className="font-medium">{entry.label}</p>
                  <p className="text-xs text-muted-foreground">{entry.description}</p>
                </div>
                <HealthBadge entry={entry} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {isAdminOrDev && <MetaAppSection />}
      {isAdminOrDev && <InstagramAppSection />}
    </div>
  );
}

// ─── Meta App credentials section (owner/admin/dev only) ────────────────
// App ID + App Secret used for the per-client Meta OAuth flow (ClienteModal).
// The secret is write-only: the backend never echoes it back, so the input
// always starts empty and is only sent when the admin actually types a new
// value. App ID is required on every save (backend contract), so it is
// requested fresh each time too — the masked value is shown only as a
// "currently set" hint, never pre-filled into the editable field.
function MetaAppSection() {
  const { data: status, loading: statusLoading, refresh } = useMetaAppStatus();
  const { save, saving } = useSaveMetaApp();
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appId.trim()) {
      toast.error("Informe o App ID do Meta.");
      return;
    }
    try {
      await save({
        app_id: appId.trim(),
        app_secret: appSecret.trim() || undefined,
      });
      setAppId("");
      setAppSecret("");
      await refresh();
    } catch {
      // useSaveMetaApp already surfaced the error toast.
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Meta App</CardTitle>
            <CardDescription>
              Credenciais do app Meta (Facebook/Instagram) usadas no OAuth
              por cliente. O App Secret nunca e reexibido depois de salvo.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {statusLoading ? (
          <div className="flex items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-sm font-medium">App ID</p>
                  <Badge
                    variant={status?.app_id_configured ? "default" : "destructive"}
                    className="gap-1 font-mono text-[11px]"
                    data-testid="meta-app-id-badge"
                  >
                    {status?.app_id_configured ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <CircleAlert className="h-3 w-3" />
                    )}
                    {status?.app_id_configured ? "configurado" : "ausente"}
                  </Badge>
                </div>
                {status?.app_id_masked && (
                  <p className="text-xs text-muted-foreground">
                    Atual: {status.app_id_masked}
                  </p>
                )}
              </div>
              <div className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-sm font-medium">App Secret</p>
                  <Badge
                    variant={status?.app_secret_configured ? "default" : "destructive"}
                    className="gap-1 font-mono text-[11px]"
                    data-testid="meta-app-secret-badge"
                  >
                    {status?.app_secret_configured ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <CircleAlert className="h-3 w-3" />
                    )}
                    {status?.app_secret_configured ? "configurado" : "ausente"}
                  </Badge>
                </div>
              </div>
            </div>

            <form
              onSubmit={handleSubmit}
              className="space-y-3"
              data-testid="meta-app-form"
            >
              <div className="space-y-1">
                <Label htmlFor="meta-app-id">App ID *</Label>
                <Input
                  id="meta-app-id"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value)}
                  placeholder="Ex: 1234567890123456"
                  disabled={saving}
                  data-testid="meta-app-id-input"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="meta-app-secret">App Secret</Label>
                <Input
                  id="meta-app-secret"
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  placeholder={
                    status?.app_secret_configured
                      ? "Deixe em branco para manter o atual"
                      : "Informe o App Secret"
                  }
                  disabled={saving}
                  data-testid="meta-app-secret-input"
                />
              </div>
              <Button type="submit" disabled={saving} data-testid="meta-app-save-btn">
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Salvar"
                )}
              </Button>
            </form>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Instagram App credentials section (owner/admin/dev only) ───────────
// App ID + App Secret for the Instagram Business Login product — a
// DIFFERENT app than the Meta (Facebook/Instagram) app above. Mirrors
// MetaAppSection exactly: the secret is write-only (never re-echoed), so
// the input always starts empty and is only sent when the admin actually
// types a new value.
function InstagramAppSection() {
  const { data: status, loading: statusLoading, refresh } = useInstagramAppStatus();
  const { save, saving } = useSaveInstagramApp();
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appId.trim()) {
      toast.error("Informe o App ID do Instagram.");
      return;
    }
    try {
      await save({
        app_id: appId.trim(),
        app_secret: appSecret.trim() || undefined,
      });
      setAppId("");
      setAppSecret("");
      await refresh();
    } catch {
      // useSaveInstagramApp already surfaced the error toast.
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Aplicativo Instagram</CardTitle>
            <CardDescription>
              App ID e App Secret do app de Instagram Business Login usado
              no OAuth do Instagram. Nao e o Facebook App ID acima nem o
              Token de Cliente — e o app cadastrado especificamente para
              login do Instagram. O App Secret nunca e reexibido depois de
              salvo.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {statusLoading ? (
          <div className="flex items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-sm font-medium">App ID</p>
                  <Badge
                    variant={status?.app_id_configured ? "default" : "destructive"}
                    className="gap-1 font-mono text-[11px]"
                    data-testid="instagram-app-id-badge"
                  >
                    {status?.app_id_configured ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <CircleAlert className="h-3 w-3" />
                    )}
                    {status?.app_id_configured ? "configurado" : "ausente"}
                  </Badge>
                </div>
                {status?.app_id_masked && (
                  <p className="text-xs text-muted-foreground">
                    Atual: {status.app_id_masked}
                  </p>
                )}
              </div>
              <div className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-sm font-medium">App Secret</p>
                  <Badge
                    variant={status?.app_secret_configured ? "default" : "destructive"}
                    className="gap-1 font-mono text-[11px]"
                    data-testid="instagram-app-secret-badge"
                  >
                    {status?.app_secret_configured ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <CircleAlert className="h-3 w-3" />
                    )}
                    {status?.app_secret_configured ? "configurado" : "ausente"}
                  </Badge>
                </div>
              </div>
            </div>

            <form
              onSubmit={handleSubmit}
              className="space-y-3"
              data-testid="instagram-app-form"
            >
              <div className="space-y-1">
                <Label htmlFor="instagram-app-id">App ID *</Label>
                <Input
                  id="instagram-app-id"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value)}
                  placeholder="Ex: 1234567890123456"
                  disabled={saving}
                  data-testid="instagram-app-id-input"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="instagram-app-secret">App Secret</Label>
                <Input
                  id="instagram-app-secret"
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  placeholder={
                    status?.app_secret_configured
                      ? "Deixe em branco para manter o atual"
                      : "Informe o App Secret"
                  }
                  disabled={saving}
                  data-testid="instagram-app-secret-input"
                />
              </div>
              <Button type="submit" disabled={saving} data-testid="instagram-app-save-btn">
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Salvar"
                )}
              </Button>
            </form>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Visibilidade de paginas tab (owner/admin/dev) ──────────────────────
// The status_pagina write-side organ lives in the seed lib and takes the
// product's own api client — see StatusPaginaPanel (@noctusai/lib).
function VisibilidadeTab() {
  return <StatusPaginaPanel api={api} enabled />;
}

// ─── Page shell ────────────────────────────────────────────────────────
export default function Settings() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdminOrDev =
    ssoCtx.isProductAdmin ||
    ssoCtx.org.role === "owner" ||
    ssoCtx.org.role === "admin" ||
    ssoCtx.org.role === "dev";

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Configuracoes</h1>
        <p className="text-sm text-muted-foreground">
          Gerencie destinatarios de notificacao e status das chaves de integracao.
        </p>
      </header>

      <Tabs defaultValue="notifications" className="w-full">
        <TabsList
          className={`grid w-full ${
            isAdminOrDev ? "grid-cols-3 sm:max-w-md" : "grid-cols-2 sm:max-w-xs"
          }`}
        >
          <TabsTrigger value="notifications">Notificacoes</TabsTrigger>
          <TabsTrigger value="keys">Chaves API</TabsTrigger>
          {isAdminOrDev && (
            <TabsTrigger value="visibilidade">Visibilidade</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="notifications" className="mt-6">
          <NotificationsTab />
        </TabsContent>
        <TabsContent value="keys" className="mt-6">
          <ApiKeysTab isAdminOrDev={isAdminOrDev} />
        </TabsContent>
        {isAdminOrDev && (
          <TabsContent value="visibilidade" className="mt-6">
            <VisibilidadeTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
