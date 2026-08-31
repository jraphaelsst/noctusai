/**
 * N8nSettingsPanel — the "Configurações" subtab: base_url, api_key
 * (write-only — the server only ever tells us `has_api_key`, never the
 * value itself), and the client's n8n tag (pick existing or create inline).
 * Renders `status` + `reachable` honestly (no silent green).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, Loader2, Plus, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateN8nTag,
  useN8nSettings,
  useN8nTags,
  useUpdateN8nSettings,
} from "@/hooks/useN8nSettings";
import { useActiveAccountId } from "@/state/useActiveAccount";

const NEW_TAG_SENTINEL = "__new__";

function ReachabilityBadge({ status, reachable }: { status: string; reachable: boolean | null }) {
  if (reachable === true) {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Conectado ({status})
      </Badge>
    );
  }
  if (reachable === false) {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Indisponível ({status})
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      <AlertCircle className="h-3 w-3" />
      {status}
    </Badge>
  );
}

export function N8nSettingsPanel() {
  const activeAccountId = useActiveAccountId("n8n");
  const settingsQuery = useN8nSettings();
  const tagsQuery = useN8nTags();
  const updateSettings = useUpdateN8nSettings();
  const createTag = useCreateN8nTag();

  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [tagSelection, setTagSelection] = useState<string>("");
  const [newTagName, setNewTagName] = useState("");

  useEffect(() => {
    if (settingsQuery.data) {
      setBaseUrl(settingsQuery.data.base_url ?? "");
      setTagSelection(settingsQuery.data.tag?.id ?? "");
    }
  }, [settingsQuery.data]);

  if (!activeAccountId) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        Selecione uma marca no seletor acima para configurar o n8n.
      </p>
    );
  }

  // `isPending` — bare, not `isLoading`: `isLoading` is `isPending &&
  // isFetching` in v5 and goes FALSE mid-refetch, which would let a
  // later branch win and unmount this form on every background
  // refetch. → KB § PATTERNS/frontend/lying-loading-state.md
  if (settingsQuery.isPending) {
    return (
      <div className="max-w-xl space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (settingsQuery.isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-destructive">
          {settingsQuery.error?.message ?? "Falha ao carregar as configurações"}
        </p>
        <Button variant="outline" size="sm" onClick={() => void settingsQuery.refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  }

  const settings = settingsQuery.data!;

  async function handleSave() {
    let resolvedTagId = tagSelection;
    try {
      if (tagSelection === NEW_TAG_SENTINEL) {
        if (!newTagName.trim()) {
          toast.error("Informe o nome da nova tag");
          return;
        }
        const tag = await createTag.mutateAsync(newTagName.trim());
        resolvedTagId = tag.id;
      }

      const body: Record<string, string> = {};
      if (baseUrl.trim()) body.base_url = baseUrl.trim();
      if (apiKey.trim()) body.api_key = apiKey.trim();
      if (resolvedTagId) body.tag_id = resolvedTagId;

      await updateSettings.mutateAsync(body);
      toast.success("Configurações salvas");
      setApiKey(""); // never keep the write-only key in local state after save
      setNewTagName("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao salvar as configurações");
    }
  }

  return (
    <Card className="max-w-xl">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Conexão n8n da marca</CardTitle>
        <ReachabilityBadge status={settings.status} reachable={settings.reachable} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="n8n-base-url">URL da instância</Label>
          <Input
            id="n8n-base-url"
            placeholder="https://n8n.exemplo.com"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="n8n-api-key">
            Chave de API {settings.has_api_key ? "(já configurada — deixe em branco para manter)" : ""}
          </Label>
          <Input
            id="n8n-api-key"
            type="password"
            placeholder={settings.has_api_key ? "••••••••" : "Cole a chave de API"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="n8n-tag">Tag da marca</Label>
          {tagsQuery.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <Select value={tagSelection} onValueChange={setTagSelection}>
              <SelectTrigger id="n8n-tag" data-testid="n8n-tag-select">
                <SelectValue placeholder="Selecione uma tag" />
              </SelectTrigger>
              <SelectContent>
                {(tagsQuery.data ?? []).map((tag) => (
                  <SelectItem key={tag.id} value={tag.id}>
                    {tag.name}
                  </SelectItem>
                ))}
                <SelectItem value={NEW_TAG_SENTINEL}>
                  <span className="flex items-center gap-1">
                    <Plus className="h-3 w-3" />
                    Criar nova tag
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          )}
          {tagSelection === NEW_TAG_SENTINEL && (
            <Input
              placeholder="Nome da nova tag"
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              autoFocus
            />
          )}
        </div>

        <Button
          onClick={() => void handleSave()}
          disabled={updateSettings.isPending || createTag.isPending}
        >
          {updateSettings.isPending || createTag.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : null}
          Salvar
        </Button>
      </CardContent>
    </Card>
  );
}
