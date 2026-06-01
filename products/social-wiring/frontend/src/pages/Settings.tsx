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

import {
  useRecipients,
  useKeysStatus,
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
function ApiKeysTab() {
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
  );
}

// ─── Page shell ────────────────────────────────────────────────────────
export default function Settings() {
  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Configuracoes</h1>
        <p className="text-sm text-muted-foreground">
          Gerencie destinatarios de notificacao e status das chaves de integracao.
        </p>
      </header>

      <Tabs defaultValue="notifications" className="w-full">
        <TabsList className="grid w-full grid-cols-2 sm:max-w-xs">
          <TabsTrigger value="notifications">Notificacoes</TabsTrigger>
          <TabsTrigger value="keys">Chaves API</TabsTrigger>
        </TabsList>

        <TabsContent value="notifications" className="mt-6">
          <NotificationsTab />
        </TabsContent>
        <TabsContent value="keys" className="mt-6">
          <ApiKeysTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
