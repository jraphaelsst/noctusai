/**
 * Edição de Fotos — Configurações (`/edicao-fotos/configuracoes`,
 * `status_pagina` row `edicao-fotos-configuracoes`, migration 128). Org edit
 * types + image-editing model (contract §8 `GET|PUT /configuracoes`,
 * `GET /modelos`). "A model-missing state blocks batch creation" (brief) —
 * that predicate is `fotosPermissions.modeloConfigurado(capacidades)`, the
 * SAME guard `NovoLote.tsx` uses, surfaced here as a banner so an admin
 * lands on the fix, not just the block.
 *
 * 🔴 Edit-role gate: the contract's role matrix (§1) ties "Org settings
 * (edit types, model, speed)" to the SAME role set as "Org dashboard" —
 * platform admin + agency admin, never corretor/curator. `Capacidades`
 * (§2) has no dedicated `pode_editar_configuracoes` field, so this page
 * infers edit access from `capacidades.dashboard !== null` (the one field
 * that already encodes exactly that admin/non-admin split). If a future
 * contract revision ships a dedicated capability, swap this inference for
 * it directly — flagged so the swap isn't missed.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` comes
 * pre-computed off `useConfiguracoes()`/`useModelos()` — never `.isLoading`.
 *
 * Notifications (plan §1): this page owns the ORG switch
 * (`notificacoes_ativas`) plus, below it, EVERY member's own per-user
 * opt-in (`MinhasNotificacoes` — not admin-gated, self-service). The
 * platform-wide switch lives on `Referencias.tsx` (the platform-settings
 * surface for this feature).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Bell, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Switch } from "@/components/ui/switch";

import {
  useAtualizarConfiguracoes,
  useAtualizarNotificacaoPreferencia,
  useCapacidades,
  useConfiguracoes,
  useModelos,
  useNotificacaoPreferencia,
  fotosPermissions,
  type LoteVelocidade,
  type NotificacaoPreferencia,
  type OrgConfiguracoes,
} from "@/hooks/useEdicaoFotos";
// Shared with the admin pages. Fixes `virtual_staging` → `staging_virtual`,
// the backend literal (the old value was refused with 422 on save).
import { TIPOS_EDICAO } from "./rotulos";


export default function Configuracoes() {
  const { capacidades } = useCapacidades();
  const configQuery = useConfiguracoes();
  const modelosQuery = useModelos();
  const atualizar = useAtualizarConfiguracoes();

  const [draft, setDraft] = useState<OrgConfiguracoes | null>(null);

  const { configuracoes, showSkeleton, error, refetch } = configQuery;

  // Seed the local draft once the real config loads — and re-seed on every
  // subsequent successful load, so an admin who saves keeps editing a form
  // that reflects what the server actually stored.
  useEffect(() => {
    if (configuracoes) setDraft(configuracoes);
  }, [configuracoes]);

  const podeEditar = fotosPermissions.dashboardScope(capacidades) !== null;
  const modeloAusente = !fotosPermissions.modeloConfigurado(capacidades);
  const economicoDisponivel = fotosPermissions.economicoDisponivel(capacidades);
  const economicoBloqueadoMotivo = fotosPermissions.economicoBloqueadoMotivo(capacidades);

  function toggleTipoEdicao(value: string) {
    if (!draft) return;
    setDraft({
      ...draft,
      tipos_edicao_ativos: draft.tipos_edicao_ativos.includes(value)
        ? draft.tipos_edicao_ativos.filter((v) => v !== value)
        : [...draft.tipos_edicao_ativos, value],
    });
  }

  async function handleSalvar() {
    if (!draft) return;
    try {
      // Explicit whitelist, NOT `draft` verbatim — `GET /configuracoes`
      // returns extra fields (`org_id`, `segue_padrao_plataforma`,
      // `limites`) this page never edits; `OrgSettingsBody` is a
      // `StrictHttpModel` (`extra="forbid"`) that 422s on an unknown key.
      await atualizar.mutateAsync({
        tipos_edicao_ativos: draft.tipos_edicao_ativos,
        modelo_editor_imagem: draft.modelo_editor_imagem,
        velocidade_padrao: draft.velocidade_padrao,
        notificacoes_ativas: draft.notificacoes_ativas,
      });
      toast.success("Configurações salvas.");
    } catch (err) {
      toast.error("Não foi possível salvar as configurações.", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Configurações</h1>
        <p className="text-sm text-muted-foreground">
          Tipos de edição ativos, modelo de IA e velocidade padrão desta organização.
        </p>
      </div>

      {modeloAusente && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <p className="text-sm">
              Nenhum modelo de edição de imagem configurado — a criação de lotes está bloqueada até um
              modelo ser escolhido abaixo.
            </p>
          </CardContent>
        </Card>
      )}

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton || !draft ? (
        <FormSkeleton />
      ) : !podeEditar ? (
        <SomenteLeitura draft={draft} />
      ) : (
        <Card>
          <CardContent className="flex flex-col gap-6 p-6">
            <div className="space-y-2">
              <Label>Tipos de edição ativos</Label>
              <div className="grid grid-cols-2 gap-2">
                {TIPOS_EDICAO.map((tipo) => (
                  <label key={tipo.value} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={draft.tipos_edicao_ativos.includes(tipo.value)}
                      onCheckedChange={() => toggleTipoEdicao(tipo.value)}
                    />
                    {tipo.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="modelo-editor">Modelo de edição de imagem</Label>
              {modelosQuery.showSkeleton ? (
                <Skeleton className="h-10 w-full" />
              ) : modelosQuery.modelos.length === 0 ? (
                <p className="text-sm text-muted-foreground" data-testid="modelos-vazio">
                  Nenhum modelo disponível no catálogo.
                </p>
              ) : (
                <Select
                  value={draft.modelo_editor_imagem ?? undefined}
                  onValueChange={(value) => setDraft({ ...draft, modelo_editor_imagem: value })}
                >
                  <SelectTrigger id="modelo-editor">
                    <SelectValue placeholder="Selecione um modelo" />
                  </SelectTrigger>
                  <SelectContent>
                    {modelosQuery.modelos.map((modelo) => (
                      <SelectItem key={modelo.id} value={modelo.id}>
                        {modelo.nome} ({modelo.versao}){modelo.suporta_batch ? " · suporta Econômico" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="velocidade-padrao">Velocidade padrão</Label>
              <Select
                value={draft.velocidade_padrao}
                onValueChange={(value) => setDraft({ ...draft, velocidade_padrao: value as LoteVelocidade })}
              >
                <SelectTrigger id="velocidade-padrao">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="urgente">Urgente</SelectItem>
                  <SelectItem value="economico" disabled={!economicoDisponivel}>
                    Econômico{!economicoDisponivel ? " (indisponível)" : ""}
                  </SelectItem>
                </SelectContent>
              </Select>
              {!economicoDisponivel && economicoBloqueadoMotivo && (
                <p className="text-xs text-muted-foreground">Motivo: {economicoBloqueadoMotivo}</p>
              )}
            </div>

            <div className="flex items-center justify-between gap-3">
              <div>
                <Label htmlFor="notificacoes-ativas">Notificações de "lote pronto"</Label>
                <p className="text-xs text-muted-foreground">
                  Desliga in-app, email e WhatsApp para esta organização (o criador continua sendo
                  notificado — este switch só afeta administradores que optaram por receber avisos).
                </p>
              </div>
              <Switch
                id="notificacoes-ativas"
                checked={draft.notificacoes_ativas}
                onCheckedChange={(v) => setDraft({ ...draft, notificacoes_ativas: v })}
              />
            </div>

            <Button onClick={handleSalvar} disabled={atualizar.isPending}>
              {atualizar.isPending ? "Salvando…" : "Salvar"}
            </Button>
          </CardContent>
        </Card>
      )}

      <MinhasNotificacoes />
    </div>
  );
}

function FormSkeleton() {
  return (
    <Card data-testid="configuracoes-loading">
      <CardContent className="flex flex-col gap-4 p-6">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
      </CardContent>
    </Card>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar as configurações.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function SomenteLeitura({ draft }: { draft: OrgConfiguracoes }) {
  return (
    <Card data-testid="configuracoes-somente-leitura">
      <CardContent className="flex flex-col gap-3 p-6">
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Lock className="h-4 w-4" /> Apenas administradores podem alterar estas configurações.
        </p>
        <p className="text-sm">
          Tipos de edição ativos:{" "}
          {draft.tipos_edicao_ativos.length > 0
            ? TIPOS_EDICAO.filter((t) => draft.tipos_edicao_ativos.includes(t.value))
                .map((t) => t.label)
                .join(", ")
            : "nenhum"}
        </p>
        <p className="text-sm">Velocidade padrão: {draft.velocidade_padrao === "urgente" ? "Urgente" : "Econômico"}</p>
        <p className="text-sm">
          Notificações de lote pronto: {draft.notificacoes_ativas ? "ligadas" : "desligadas"}
        </p>
      </CardContent>
    </Card>
  );
}

/**
 * Plan §1: "agency admins opt in per user" + "the creator is always
 * notified". Self-service — ANY authenticated member (not admin-gated):
 * `ativo` only matters if the caller IS an agency admin (the fan-out
 * ignores it otherwise, `services/notifier.py`), but every member can
 * register a WhatsApp number here for when THEY create a batch.
 */
function MinhasNotificacoes() {
  const { preferencia, showSkeleton, error, refetch } = useNotificacaoPreferencia();
  const atualizar = useAtualizarNotificacaoPreferencia();
  const [draft, setDraft] = useState<NotificacaoPreferencia | null>(null);

  useEffect(() => {
    if (preferencia) setDraft(preferencia);
  }, [preferencia]);

  async function handleSalvar() {
    if (!draft) return;
    try {
      await atualizar.mutateAsync(draft);
      toast.success("Preferência de notificação salva.");
    } catch (err) {
      toast.error("Não foi possível salvar.", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">Minhas notificações</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Quando um lote que VOCÊ criou fica pronto você é sempre avisado. Ligue abaixo para
          também ser avisado de lotes de outras pessoas da organização (só tem efeito se você for
          administrador da agência).
        </p>
        {error ? (
          <ErrorState onRetry={() => refetch()} />
        ) : showSkeleton || !draft ? (
          <div data-testid="minhas-notificacoes-loading">
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="notificacao-preferencia-ativo">
                Avisar sobre lotes de outras pessoas
              </Label>
              <Switch
                id="notificacao-preferencia-ativo"
                checked={draft.ativo}
                onCheckedChange={(v) => setDraft({ ...draft, ativo: v })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notificacao-preferencia-whatsapp">Número de WhatsApp</Label>
              <Input
                id="notificacao-preferencia-whatsapp"
                type="tel"
                placeholder="+5511999998888"
                value={draft.whatsapp_number ?? ""}
                onChange={(e) => setDraft({ ...draft, whatsapp_number: e.target.value || null })}
              />
              <p className="text-xs text-muted-foreground">
                Formato internacional (E.164), ex.: +5511999998888. Deixe em branco para não
                receber avisos por WhatsApp.
              </p>
            </div>
            <div>
              <Button onClick={handleSalvar} disabled={atualizar.isPending} variant="outline">
                {atualizar.isPending ? "Salvando…" : "Salvar preferência"}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
