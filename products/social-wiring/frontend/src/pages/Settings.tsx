/**
 * Settings page — multi-tab configuration cockpit.
 *
 *   Notifications tab    SMTP + WAHA status (read-only) + recipient CRUD
 *   API Keys tab         Org keys the operator SETS here (encrypted at rest,
 *                         /api/settings/api-keys) + read-only health badges
 *                         for the deployment's .env (/api/settings/keys/status)
 *   Clientes tab         Inactivity-sweep threshold (D16) — read open to any
 *                         org member, write admin-gated (see ClientesInactivityTab)
 *
 * NOTE: The YouTube connection tab was removed — YouTube accounts are now
 * managed in the unified Conexoes page (/conexoes).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  CircleAlert,
  Clock,
  Loader2,
  Plus,
  Trash2,
  Mail,
  MessageCircle,
  KeyRound,
  Pencil,
  Plug,
  RotateCcw,
  ShieldCheck,
  CalendarDays,
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
  useApiKeys,
  useSaveApiKey,
  useRemoveApiKey,
  useTestApiKey,
  type ApiKeySource,
  type ApiKeyStatus,
  type ApiKeyTestResult,
  useMetaAppStatus,
  useSaveMetaApp,
  useInstagramAppStatus,
  useSaveInstagramApp,
  useClientesInactivityConfig,
  useSaveClientesInactivityConfig,
  useDocumentoRetencao,
  useSaveDocumentoRetencao,
  useResetDocumentoRetencao,
  type DocumentoRetencaoPolitica,
  type KeyStatusEntry,
  type Recipient,
  type RecipientCreate,
  useCalendarStatus,
  fetchCalendarAuthUrl,
} from "@/hooks/useSettings";
import { useMarcas, type Marca } from "@/hooks/useMarcas";
import { rotuloTipo } from "@/lib/documentoTipos";

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
  marca_id: null,
};

/** Sentinel for the org-wide tier in the <select>. A DOM select cannot hold
 *  `null`, and "" is indistinguishable from "nothing chosen yet" — so the
 *  absence of a client is given an explicit value rather than being inferred
 *  from an empty string. */
const ORG_WIDE = "__org__";

function NotificationsTab() {
  const { data, loading, create, update, remove } = useRecipients();
  const { data: keys } = useKeysStatus();
  const { data: marcas = [] } = useMarcas();
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
        marca_id: draft.marca_id ?? null,
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
          <CardTitle>Canais de notificação</CardTitle>
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
          <CardTitle>Destinatários</CardTitle>
          <CardDescription>
            Lista fixa que recebe a notificação em cada upload publicado.
            No momento do upload dá para desmarcar individualmente.
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
            <select
              className="h-10 rounded-md border bg-background px-2 text-sm sm:col-span-3"
              aria-label="Marca do destinatário"
              value={draft.marca_id ?? ORG_WIDE}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  marca_id: e.target.value === ORG_WIDE ? null : e.target.value,
                })
              }
            >
              <option value={ORG_WIDE}>Todos os marcas (geral)</option>
              {marcas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
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
                  marcas={marcas}
                  onToggleActive={(active) =>
                    update(r.id, { is_active: active })
                  }
                  onChangeClient={(marcaId) =>
                    update(r.id, { marca_id: marcaId })
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
  marcas,
  onToggleActive,
  onChangeClient,
  onDelete,
}: {
  recipient: Recipient;
  marcas: Marca[];
  onToggleActive: (active: boolean) => void;
  onChangeClient: (marcaId: string | null) => void;
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
        {/* Scope is editable in place. Sending null clears it back to the
            org-wide tier — the backend distinguishes an explicit null from an
            omitted key, so this genuinely un-scopes rather than no-ops. */}
        <select
          className="h-8 rounded-md border bg-background px-2 text-xs"
          aria-label={`Marca de ${recipient.name}`}
          value={recipient.marca_id ?? ORG_WIDE}
          onChange={(e) =>
            onChangeClient(e.target.value === ORG_WIDE ? null : e.target.value)
          }
        >
          <option value={ORG_WIDE}>Todos os marcas</option>
          {marcas.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
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
/**
 * Google Calendar connection.
 *
 * `/api/calendar/status` + `/oauth/start` shipped with no UI: there was no way
 * to see whether consent had been given, and no way to give it. The scheduling
 * module writes `google_calendar_event_id` on its appointments, so this is the
 * switch that makes those writes land somewhere real.
 */
function CalendarCard() {
  const { data, loading, error, refresh } = useCalendarStatus();
  const [connecting, setConnecting] = useState(false);

  async function connect() {
    setConnecting(true);
    try {
      const url = await fetchCalendarAuthUrl();
      // The browser must do this navigation, not fetch — it is a consent
      // screen on Google's origin.
      window.open(url, "_blank", "noopener,noreferrer");
      toast.info("Conclua o consentimento na aba aberta e atualize o status.");
    } catch (err: unknown) {
      toast.error("Não foi possível iniciar a conexão com o Google.", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setConnecting(false);
    }
  }

  return (
    <Card data-testid="calendar-card">
      <CardHeader>
        <div className="flex items-center gap-3">
          <CalendarDays className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Google Calendar</CardTitle>
            <CardDescription>
              Conexão usada pelo agendador para gravar as visitas na agenda.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div
            className="flex items-center justify-center p-6"
            data-testid="calendar-loading"
          >
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <p className="text-sm text-destructive" data-testid="calendar-error">
            {error}
          </p>
        ) : !data ? (
          <p
            className="text-sm text-muted-foreground"
            data-testid="calendar-empty"
          >
            Status do calendário indisponível.
          </p>
        ) : (
          <div className="space-y-2 text-sm" data-testid="calendar-status">
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Adaptador</span>
              <span className="font-medium">{data.adapter}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Conectado</span>
              <span className="font-medium">
                {data.configured ? "Sim" : "Não"}
              </span>
            </div>
            {data.account_email && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">Conta</span>
                <span className="font-medium">{data.account_email}</span>
              </div>
            )}
            {data.default_timezone && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">Fuso padrão</span>
                <span className="font-medium">{data.default_timezone}</span>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {data?.consent_required && (
            <Button
              onClick={() => void connect()}
              disabled={connecting}
              data-testid="calendar-connect"
            >
              {connecting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <CalendarDays className="mr-2 h-4 w-4" />
              )}
              Conectar Google Calendar
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() => void refresh()}
            disabled={loading}
            data-testid="calendar-refresh"
          >
            Atualizar status
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── API keys tab ───────────────────────────────────────────────────────
// TWO halves in one card, on purpose:
//   · the MANAGED keys — set here, encrypted at rest, per-org. These are
//     what the certidões / matrículas workflows resolve.
//   · the ENVIRONMENT health list — read-only status of what the running
//     deployment carries in its .env. Kept, not replaced: it is the only
//     place an operator can see that e.g. WAHA or SMTP is unwired.
const API_KEY_SOURCE_LABEL: Record<ApiKeySource, string> = {
  local: "salva neste produto",
  platform: "configurada na plataforma",
  env: "vinda do ambiente (.env)",
};

function ManagedApiKeyRow({
  item,
  canEdit,
}: {
  item: ApiKeyStatus;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [testResult, setTestResult] = useState<ApiKeyTestResult | null>(null);

  const save = useSaveApiKey();
  const remove = useRemoveApiKey();
  const test = useTestApiKey();

  const cancel = () => {
    setEditing(false);
    setValue("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      toast.error("Informe um valor.");
      return;
    }
    try {
      await save.mutateAsync({ key: item.key, value: value.trim() });
      // Write-only: the backend never returns the value, so the field is
      // cleared rather than re-populated from the response.
      cancel();
      setTestResult(null);
    } catch {
      /* toast already surfaced by the hook's onError */
    }
  };

  const handleRemove = async () => {
    try {
      await remove.mutateAsync(item.key);
      setTestResult(null);
    } catch {
      /* toast already surfaced by the hook's onError */
    }
  };

  const handleTest = async () => {
    setTestResult(null);
    try {
      setTestResult(await test.mutateAsync(item.key));
    } catch (err: any) {
      setTestResult({
        key: item.key,
        success: false,
        message: err?.message ?? "Erro desconhecido.",
      });
    }
  };

  return (
    <div className="space-y-2 px-4 py-3" data-testid={`api-key-${item.key}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm">{item.label}</p>
          <p className="text-xs text-muted-foreground">{item.description}</p>
        </div>
        <Badge
          variant={item.configured ? "default" : "secondary"}
          className="gap-1 shrink-0 text-[11px]"
          data-testid={`api-key-badge-${item.key}`}
        >
          {item.configured ? (
            <CheckCircle2 className="h-3 w-3" />
          ) : (
            <CircleAlert className="h-3 w-3" />
          )}
          {item.configured ? "configurada" : "não configurada"}
        </Badge>
      </div>

      {item.configured && !editing && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <code
            className="rounded bg-muted px-2 py-1 font-mono"
            data-testid={`api-key-hint-${item.key}`}
          >
            {item.hint}
          </code>
          {item.source && (
            <span
              className="text-muted-foreground"
              data-testid={`api-key-source-${item.key}`}
            >
              {API_KEY_SOURCE_LABEL[item.source]}
            </span>
          )}
        </div>
      )}

      {!editing && (
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setEditing(true)}
              data-testid={`api-key-edit-${item.key}`}
            >
              <Pencil className="mr-1 h-3.5 w-3.5" />
              {item.configured ? "Substituir" : "Configurar"}
            </Button>
          )}
          {/* Removal only makes sense for a LOCAL override — a platform /
              .env value is not this screen's to delete, and offering the
              button would promise something the endpoint cannot do. */}
          {canEdit && item.source === "local" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-red-600"
              onClick={handleRemove}
              disabled={remove.isPending}
              data-testid={`api-key-remove-${item.key}`}
            >
              {remove.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="mr-1 h-3.5 w-3.5" />
              )}
              Remover
            </Button>
          )}
          {item.testable && item.configured && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={handleTest}
              disabled={test.isPending}
              data-testid={`api-key-test-${item.key}`}
            >
              {test.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plug className="mr-1 h-3.5 w-3.5" />
              )}
              {test.isPending ? "Testando..." : "Testar"}
            </Button>
          )}
        </div>
      )}

      {editing && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={submit}
          data-testid={`api-key-form-${item.key}`}
        >
          <Input
            autoFocus
            type={item.input_type}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") cancel();
            }}
            placeholder={item.placeholder}
            className="h-8 flex-1 min-w-[220px] text-sm"
            data-testid={`api-key-input-${item.key}`}
          />
          <Button
            type="submit"
            size="sm"
            className="h-8 text-xs"
            disabled={save.isPending || !value.trim()}
          >
            {save.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : null}
            {save.isPending ? "Salvando..." : "Salvar"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 text-xs"
            onClick={cancel}
          >
            Cancelar
          </Button>
        </form>
      )}

      {testResult && !editing && (
        <p
          className={`text-xs font-medium ${
            testResult.success ? "text-green-600" : "text-red-600"
          }`}
          data-testid={`api-key-test-result-${item.key}`}
        >
          {testResult.message}
        </p>
      )}
    </div>
  );
}

function ManagedApiKeysSection({ canEdit }: { canEdit: boolean }) {
  // 🔴 Two signals, never `isLoading`: the skeleton is for the FIRST load
  // only; a refetch over data already on screen shows a quiet indicator
  // instead of blanking the list.
  const { data, showSkeleton, isRefreshing, isError, refetch } = useApiKeys();

  if (showSkeleton) {
    return (
      <div
        className="flex items-center justify-center p-8"
        data-testid="api-keys-skeleton"
      >
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError && !data) {
    return (
      <div className="space-y-2 p-6 text-center" data-testid="api-keys-error">
        <p className="text-sm text-muted-foreground">
          Nao foi possivel carregar as chaves configuraveis.
        </p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          <RotateCcw className="mr-1 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  const items = data?.items ?? [];
  if (items.length === 0) {
    return (
      <p className="p-6 text-center text-sm text-muted-foreground">
        Nenhuma chave configuravel neste produto.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">Configuraveis nesta tela</p>
        {isRefreshing && (
          <span
            className="flex items-center gap-1 text-xs text-muted-foreground"
            data-testid="api-keys-refreshing"
          >
            <Loader2 className="h-3 w-3 animate-spin" />
            atualizando
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Salvas criptografadas e usadas pelas rotinas de certidoes, matriculas
        e IA desta organizacao.
        {!canEdit && " Somente owner/admin podem alterar."}
      </p>
      <div className="divide-y rounded-md border">
        {items.map((item) => (
          <ManagedApiKeyRow key={item.key} item={item} canEdit={canEdit} />
        ))}
      </div>
    </div>
  );
}

function EnvKeysHealthList() {
  const { data, loading } = useKeysStatus();

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!data) {
    return (
      <p className="p-6 text-center text-sm text-muted-foreground">
        Nao foi possivel carregar o status das chaves.
      </p>
    );
  }

  const entries: [keyof typeof data, KeyStatusEntry][] = Object.entries(
    data
  ) as [keyof typeof data, KeyStatusEntry][];

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Status do ambiente (.env)</p>
      <p className="text-xs text-muted-foreground">
        Somente leitura. Para alterar, edite o arquivo e reinicie o backend.
      </p>
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
    </div>
  );
}

function ApiKeysTab({ isAdminOrDev }: { isAdminOrDev: boolean }) {
  return (
    <div className="space-y-6">
      <CalendarCard />
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <KeyRound className="h-5 w-5 text-muted-foreground" />
            <div>
              <CardTitle>Chaves de API</CardTitle>
              <CardDescription>
                Chaves da organizacao, salvas criptografadas neste produto —
                mais o status (somente leitura) do que o ambiente carrega.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <ManagedApiKeysSection canEdit={isAdminOrDev} />
          <Separator />
          <EnvKeysHealthList />
        </CardContent>
      </Card>

      {isAdminOrDev && <MetaAppSection />}
      {isAdminOrDev && <InstagramAppSection />}
    </div>
  );
}

// ─── Meta App credentials section (owner/admin/dev only) ────────────────
// App ID + App Secret used for the per-marca Meta OAuth flow (MarcaModal).
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
              por marca. O App Secret nunca e reexibido depois de salvo.
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

// ─── Clientes inactivity threshold tab (D16, roadmap lead-card-hub-2026-08) ─
// Read is open to any authenticated org member (mirrors the backend split
// documented in `settings_router.py`); only the write is admin-gated. So
// unlike MetaAppSection/InstagramAppSection above (hidden entirely from a
// non-admin), this section is always rendered — a non-admin sees the
// effective value read-only rather than a form that would 403 on submit.
//
// `canEdit` is checked against `org.role` directly (owner/admin), NOT the
// broader `isAdminOrDev` flag the sibling sections use — the backend's
// `_require_admin` only accepts owner/admin, and showing an editable form
// to a role the backend will reject is exactly the "let them submit and
// eat a 403" outcome this slice's brief calls out. See this dispatch's
// `drift-found:` note re: MetaAppSection/InstagramAppSection using the
// broader flag against the same admin-only backend gate.
//
// State coverage: loading (spinner) / error (retry) / success, with the
// "unconfigured — falling back to the platform default" case standing in
// for "empty" (there is no list here to be literally empty; an org that
// never set its own value is the closest analogue, and is rendered
// distinctly from both "configured" and "disabled").
function ClientesInactivityTab({ canEdit }: { canEdit: boolean }) {
  const { data, loading, isError, refetch } = useClientesInactivityConfig();
  const { mutate: save, isPending: saving } = useSaveClientesInactivityConfig();
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);

  // Keep the draft synced to the resolved server value — but only until the
  // admin starts typing, so a background refetch never stomps an in-flight
  // edit.
  useEffect(() => {
    if (data && !dirty) {
      setDraft(String(data.threshold_days));
    }
  }, [data, dirty]);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center p-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
          <p className="text-sm text-muted-foreground">
            Não foi possível carregar o limite de inatividade de clientes.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            data-testid="clientes-inactivity-retry-btn"
          >
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  const disabledForOrg = data.threshold_days === 0;
  const parsedDraft = Number(draft);
  const isValid =
    draft.trim() !== "" && Number.isInteger(parsedDraft) && parsedDraft >= 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) {
      toast.error("Informe um número inteiro maior ou igual a 0.");
      return;
    }
    save(parsedDraft, { onSuccess: () => setDirty(false) });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Clock className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Inatividade de clientes</CardTitle>
            <CardDescription>
              Clientes sem contato há mais de N dias são marcados como
              inativos e saem do quadro; podem ser restaurados a qualquer
              momento.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border p-3" data-testid="clientes-inactivity-status">
          <div className="mb-1 flex items-center justify-between">
            <p className="text-sm font-medium">Limite atual</p>
            <Badge
              variant={disabledForOrg ? "destructive" : "default"}
              className="gap-1 font-mono text-[11px]"
              data-testid="clientes-inactivity-status-badge"
            >
              {disabledForOrg ? (
                <CircleAlert className="h-3 w-3" />
              ) : (
                <CheckCircle2 className="h-3 w-3" />
              )}
              {disabledForOrg
                ? "desativado"
                : data.configured
                  ? "personalizado"
                  : "padrao da plataforma"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {disabledForOrg
              ? "A varredura automatica esta desativada para esta organizacao — nenhum cliente e marcado como inativo automaticamente."
              : data.configured
                ? `${data.threshold_days} dia(s) sem contato ate marcar como inativo.`
                : `${data.default_threshold_days} dia(s) sem contato (padrao da plataforma — esta organizacao ainda nao personalizou este valor).`}
          </p>
        </div>

        {!canEdit && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="clientes-inactivity-readonly-note"
          >
            Somente administradores da organizacao podem alterar este valor.
          </p>
        )}

        {canEdit && (
          <form
            onSubmit={handleSubmit}
            className="space-y-3"
            data-testid="clientes-inactivity-form"
          >
            <div className="space-y-1">
              <Label htmlFor="clientes-inactivity-days">
                Dias sem contato ate marcar como inativo
              </Label>
              <Input
                id="clientes-inactivity-days"
                type="number"
                min={0}
                step={1}
                inputMode="numeric"
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setDirty(true);
                }}
                disabled={saving}
                data-testid="clientes-inactivity-input"
              />
              <p className="text-xs text-muted-foreground">
                Use 0 para desativar a varredura automatica nesta
                organizacao. Clientes marcados como inativos automaticamente
                podem ser restaurados a qualquer momento na aba Inativos do
                quadro de Clientes.
              </p>
            </div>
            <Button
              type="submit"
              disabled={saving || !isValid}
              data-testid="clientes-inactivity-save-btn"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Salvar"}
            </Button>
          </form>
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
// ─── Document retention tab (migration 079) ─────────────────────────────
//
// The screen the owner asked for: "leave a UI for it so i can change it later
// if i need to". Every document type, its effective retention, the platform
// default behind it, and a restore.
//
// 🔴 IT ALWAYS SHOWS THE ANCHOR. A retention period is a duration and a
// duration alone is ambiguous — "5 anos" counted from the upload and from the
// deal's close are years apart, and the atendimento surface counts from the
// close because Lei 9.613/98 art. 10 III says "da conclusão da transação".
// Rendering the number without `ancora_rotulo` would be a screen that reads
// correctly and means something else.

const SUPERFICIE_ROTULOS: Record<string, string> = {
  cliente: "Documentos do cliente",
  atendimento: "Documentos do atendimento (negociação)",
};

/** `null` is "manter indefinidamente" — a real policy, never a blank. */
function formatRetencao(dias: number | null): string {
  if (dias === null) return "Indefinidamente";
  if (dias % 365 === 0) {
    const anos = dias / 365;
    return `${dias} dias (${anos} ${anos === 1 ? "ano" : "anos"})`;
  }
  return `${dias} dias`;
}

/** Sentinel for the "manter indefinidamente" option. A DOM input cannot hold
 *  `null`, and "" is indistinguishable from "the field is empty because I am
 *  still typing" — so the absence of a clock gets an explicit value. */
const INDEFINIDO = "__indefinido__";

function RetencaoLinha({
  politica,
  canEdit,
}: {
  politica: DocumentoRetencaoPolitica;
  canEdit: boolean;
}) {
  const { mutate: save, isPending: saving } = useSaveDocumentoRetencao();
  const { mutate: reset, isPending: resetting } = useResetDocumentoRetencao();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const iniciar = () => {
    setDraft(
      politica.retencao_dias === null ? INDEFINIDO : String(politica.retencao_dias)
    );
    setEditing(true);
  };

  const submeter = (e: React.FormEvent) => {
    e.preventDefault();
    const indefinido = draft === INDEFINIDO;
    const parsed = Number(draft);
    if (!indefinido && (!Number.isInteger(parsed) || parsed < 1)) {
      toast.error("Informe um número inteiro de 1 dia ou mais.");
      return;
    }
    save(
      {
        superficie: politica.superficie,
        tipo_documento: politica.tipo_documento,
        retencao_dias: indefinido ? null : parsed,
      },
      { onSuccess: () => setEditing(false) }
    );
  };

  return (
    <div
      className="flex flex-col gap-2 border-b py-3 last:border-b-0"
      data-testid={`retencao-row-${politica.superficie}-${politica.tipo_documento}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          {/* The human label leads; the slug stays visible underneath because
              it is what the API, the storage path and any support question
              actually name. Showing only the slug — as this screen first did —
              is the same defect the imóvel filters have. */}
          <p className="text-sm font-medium">
            {rotuloTipo(politica.superficie, politica.tipo_documento)}
          </p>
          <p className="text-xs text-muted-foreground">
            <span className="font-mono">{politica.tipo_documento}</span>
            {" · "}
            {politica.ancora_rotulo}
          </p>
        </div>
        {!editing && (
          <div className="flex items-center gap-2">
            <span className="text-sm">{formatRetencao(politica.retencao_dias)}</span>
            {politica.personalizado && (
              <Badge variant="secondary" className="text-[11px]">
                personalizado
              </Badge>
            )}
            {canEdit && (
              <Button
                variant="outline"
                size="sm"
                onClick={iniciar}
                data-testid={`retencao-alterar-${politica.tipo_documento}`}
              >
                Alterar
              </Button>
            )}
            {canEdit && politica.personalizado && (
              <Button
                variant="ghost"
                size="sm"
                disabled={resetting}
                title={`Restaurar o padrão da plataforma (${formatRetencao(
                  politica.padrao_dias
                )})`}
                aria-label={`Restaurar o padrão de ${rotuloTipo(politica.superficie, politica.tipo_documento)}`}
                onClick={() =>
                  reset({
                    superficie: politica.superficie,
                    tipo_documento: politica.tipo_documento,
                  })
                }
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )}
      </div>

      {/* The default and the reason behind it — an audit asks "why this
          number", and a bare integer answers nothing. */}
      {politica.personalizado && (
        <p className="text-xs text-muted-foreground">
          Padrão da plataforma: {formatRetencao(politica.padrao_dias)}
        </p>
      )}
      {politica.padrao_motivo && !politica.personalizado && (
        <p className="text-xs text-muted-foreground">{politica.padrao_motivo}</p>
      )}

      {editing && (
        <form onSubmit={submeter} className="flex flex-wrap items-center gap-2">
          <Input
            type="text"
            inputMode="numeric"
            className="h-8 w-32"
            value={draft === INDEFINIDO ? "" : draft}
            placeholder="dias"
            onChange={(e) => setDraft(e.target.value)}
            aria-label={`Retenção em dias para ${rotuloTipo(politica.superficie, politica.tipo_documento)}`}
          />
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Switch
              checked={draft === INDEFINIDO}
              onCheckedChange={(on) => setDraft(on ? INDEFINIDO : "")}
            />
            Manter indefinidamente
          </label>
          <Button
            type="submit"
            size="sm"
            disabled={saving}
            data-testid={`retencao-salvar-${politica.tipo_documento}`}
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Salvar"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setEditing(false)}
          >
            Cancelar
          </Button>
        </form>
      )}
    </div>
  );
}

function DocumentoRetencaoTab({ canEdit }: { canEdit: boolean }) {
  const { data, loading, isError, refetch } = useDocumentoRetencao();

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center p-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
          <p className="text-sm text-muted-foreground">
            Não foi possível carregar a política de retenção de documentos.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            data-testid="documento-retencao-retry-btn"
          >
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  const grupos = ["atendimento", "cliente"].filter((s) =>
    data.items.some((p) => p.superficie === s)
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-muted-foreground" />
            <div>
              <CardTitle>Retenção de documentos</CardTitle>
              <CardDescription>
                Por quanto tempo cada tipo de documento é mantido antes de ser
                removido automaticamente. A contagem só começa a partir do
                marco indicado em cada linha.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        {!canEdit && (
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Somente owner ou admin podem alterar estes prazos.
            </p>
          </CardContent>
        )}
      </Card>

      {grupos.map((superficie) => (
        <Card key={superficie}>
          <CardHeader>
            <CardTitle className="text-base">
              {SUPERFICIE_ROTULOS[superficie] ?? superficie}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {data.items
              .filter((p) => p.superficie === superficie)
              .map((p) => (
                <RetencaoLinha
                  key={`${p.superficie}:${p.tipo_documento}`}
                  politica={p}
                  canEdit={canEdit}
                />
              ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdminOrDev =
    ssoCtx.isProductAdmin ||
    ssoCtx.org.role === "owner" ||
    ssoCtx.org.role === "admin" ||
    ssoCtx.org.role === "dev";
  // Precise owner/admin check for the clientes-inactivity write form — the
  // backend's `_require_admin` accepts only these two roles (not "dev"),
  // so this stays narrower than `isAdminOrDev` on purpose. See
  // ClientesInactivityTab's header comment.
  const canEditClientesInactivity =
    ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Configurações</h1>
        <p className="text-sm text-muted-foreground">
          Gerencie destinatários de notificação e status das chaves de integração.
        </p>
      </header>

      <Tabs defaultValue="notifications" className="w-full">
        <TabsList
          className={`grid w-full ${
            isAdminOrDev ? "grid-cols-5 sm:max-w-2xl" : "grid-cols-4 sm:max-w-lg"
          }`}
        >
          <TabsTrigger value="notifications">Notificações</TabsTrigger>
          <TabsTrigger value="keys">Chaves API</TabsTrigger>
          <TabsTrigger value="clientes">Clientes</TabsTrigger>
          <TabsTrigger value="retencao">Retenção</TabsTrigger>
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
        <TabsContent value="clientes" className="mt-6">
          <ClientesInactivityTab canEdit={canEditClientesInactivity} />
        </TabsContent>
        {/* Read is open to any member — a corretor should be able to look up
            how long we keep a buyer's income tax return. Only the write is
            narrowed to owner/admin, matching the backend's `_require_admin`. */}
        <TabsContent value="retencao" className="mt-6">
          <DocumentoRetencaoTab canEdit={canEditClientesInactivity} />
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
