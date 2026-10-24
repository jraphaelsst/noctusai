/**
 * SimecConfigEditor — edits ONE override layer of the SIMEC config (org or
 * profile), per the contract (`PUT /api/simec/config/org` ·
 * `PUT /api/simec/accounts/{id}/config`).
 *
 * - The layer is edited as a minimal override object over the layer BELOW it
 *   (org layer → seed defaults; profile layer → org-effective config). A value
 *   equal to the layer below is not stored.
 * - Every item has "Restaurar padrão" (drops that item's overrides from the
 *   draft); "Salvar" PUTs the WHOLE layer (the endpoint replaces it).
 * - Owner/admin only (`useIsOrgAdmin`, UX gate — the server enforces with a
 *   403); everyone else sees the same form read-only.
 * - Override paths this form does not edit (lists, labels, new keys added
 *   elsewhere) are preserved untouched in the draft.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { RotateCcw, Save } from "lucide-react";
import { ErrorState, FormError, Select, Skeleton } from "@noctusai/lib/design-system";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSaveSimecConfig, useSimecConfig, useSimecDefaults } from "@/hooks/useSimec";
import {
  applyFieldEdit,
  getPath,
  hasAnyPath,
  restoreItem,
  sameOverrides,
  simecErrorMessage,
  type Overrides,
  type Path,
  type SimecConfig,
  type SimecLayer,
} from "@/lib/simec";
import { useBeforeUnloadGuard } from "@noctusai/lib/components";

// ─── Item model ─────────────────────────────────────────────────────────────

type FieldKind = "number" | "bool" | "select";
interface FieldDef {
  path: Path;
  label: string;
  kind: FieldKind;
  step?: number;
  options?: { value: string; label: string }[];
}
interface ItemDef {
  id: string;
  title: string;
  fields: FieldDef[];
}
interface SectionDef {
  key: string;
  title: string;
  items: ItemDef[];
}

const METHOD_OPTIONS = [
  { value: "pct_from_median", label: "% da mediana" },
  { value: "outside_iqr", label: "fora do intervalo interquartil (IQR)" },
];
const DIRECTION_OPTIONS = [
  { value: "both", label: "acima ou abaixo" },
  { value: "above", label: "só acima" },
  { value: "below", label: "só abaixo" },
];

function keysOf(base: unknown, draft: unknown, coll: string): string[] {
  const a = Object.keys((getPath(base, [coll]) as object) ?? {});
  const b = Object.keys((getPath(draft, [coll]) as object) ?? {});
  return [...a, ...b.filter((k) => !a.includes(k))];
}

function labelAt(base: unknown, draft: unknown, coll: string, key: string): string {
  const v = getPath(draft, [coll, key, "label"]) ?? getPath(base, [coll, key, "label"]);
  return typeof v === "string" && v ? v : key;
}

/** Sections derived from the config itself — a new config key gets a row with no FE change. */
export function buildSections(base: SimecConfig, draft: Overrides): SectionDef[] {
  const per = (coll: string, fields: (k: string) => FieldDef[]): ItemDef[] =>
    keysOf(base, draft, coll).map((k) => ({
      id: `${coll}.${k}`,
      title: labelAt(base, draft, coll, k),
      fields: fields(k),
    }));
  const reviews = Object.keys(base.cadence?.reviews ?? {});
  return [
    {
      key: "windows",
      title: "Janelas de leitura",
      items: per("windows", (k) => [
        { path: ["windows", k, "enabled"], label: "Ativa", kind: "bool" },
        { path: ["windows", k, "min_days"], label: "Dia mínimo", kind: "number", step: 1 },
        { path: ["windows", k, "max_days"], label: "Dia máximo", kind: "number", step: 1 },
      ]),
    },
    {
      key: "metrics",
      title: "Métricas fornecidas pela plataforma",
      items: per("metrics", (k) => [
        { path: ["metrics", k, "available"], label: "Disponível", kind: "bool" },
      ]),
    },
    {
      key: "indicators",
      title: "Indicadores",
      items: per("indicators", (k) => [
        { path: ["indicators", k, "enabled"], label: "Calcular", kind: "bool" },
      ]),
    },
    {
      key: "panel",
      title: "Linhas do painel",
      items: per("panel", (k) => [{ path: ["panel", k, "enabled"], label: "Exibir", kind: "bool" }]),
    },
    {
      key: "baseline",
      title: "Linha de base (histórico do próprio perfil)",
      items: [
        {
          id: "baseline",
          title: "Histórico comparável",
          fields: [
            { path: ["baseline", "lookback_days"], label: "Dias de histórico", kind: "number", step: 1 },
            { path: ["baseline", "min_posts"], label: "Amostra mínima (posts)", kind: "number", step: 1 },
          ],
        },
      ],
    },
    {
      key: "alerts",
      title: "Alertas (relativos ao padrão do perfil)",
      items: per("alerts", (k) => [
        { path: ["alerts", k, "enabled"], label: "Ativo", kind: "bool" },
        { path: ["alerts", k, "method"], label: "Método", kind: "select", options: METHOD_OPTIONS },
        { path: ["alerts", k, "threshold"], label: "Limiar", kind: "number", step: 0.05 },
        { path: ["alerts", k, "direction"], label: "Direção", kind: "select", options: DIRECTION_OPTIONS },
      ]).map((it) => ({ ...it, title: alertTitle(base, draft, it.id.slice("alerts.".length)) })),
    },
    {
      key: "cadence",
      title: "Cadência",
      items: [
        ...reviews.map((k) => ({
          id: `cadence.${k}`,
          title: (getPath(base, ["cadence", "reviews", k, "label"]) as string) ?? k,
          fields: [
            { path: ["cadence", "reviews", k, "every_days"], label: "Período (dias)", kind: "number" as const, step: 1 },
          ],
        })),
        {
          id: "cadence.decision",
          title: "Validação de decisões",
          fields: [
            { path: ["cadence", "decision_validation_days"], label: "Dias até avaliar", kind: "number", step: 1 },
          ],
        },
      ],
    },
  ];
}

function alertTitle(base: unknown, draft: unknown, key: string): string {
  const ind = (getPath(draft, ["alerts", key, "indicator"]) ?? getPath(base, ["alerts", key, "indicator"])) as
    | string
    | undefined;
  const indLabel = ind ? ((getPath(base, ["indicators", ind, "label"]) ?? getPath(base, ["metrics", ind, "label"])) as string | undefined) : undefined;
  return indLabel ? `${key} — ${indLabel}` : key;
}

// ─── Field rendering ────────────────────────────────────────────────────────

function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: FieldDef;
  value: unknown;
  disabled: boolean;
  onChange: (v: unknown) => void;
}) {
  const id = `simec-cfg-${field.path.join("-")}`;
  if (field.kind === "bool") {
    return (
      <label htmlFor={id} className="flex items-center gap-2 text-sm">
        <input
          id={id}
          type="checkbox"
          checked={value !== false}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          aria-label={field.label}
        />
        {field.label}
      </label>
    );
  }
  if (field.kind === "select") {
    return (
      <label htmlFor={id} className="flex flex-col gap-1 text-xs">
        {field.label}
        <Select id={id} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={field.label}>
          {(field.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </label>
    );
  }
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs">
      {field.label}
      <input
        id={id}
        type="number"
        step={field.step ?? 1}
        className="h-8 w-28 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
        value={typeof value === "number" ? String(value) : ""}
        disabled={disabled}
        aria-label={field.label}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    </label>
  );
}

// ─── Layer form ─────────────────────────────────────────────────────────────

function LayerForm({
  base,
  layer,
  accountId,
  canEdit,
  restoreHint,
}: {
  base: SimecConfig;
  layer: SimecLayer | null;
  accountId: string | null;
  canEdit: boolean;
  restoreHint: string;
}) {
  const saved = useMemo(() => layer?.overrides ?? {}, [layer]);
  const [draft, setDraft] = useState<Overrides>(saved);
  const save = useSaveSimecConfig();
  const sections = useMemo(() => buildSections(base, draft), [base, draft]);
  const dirty = !sameOverrides(draft, saved);
  // "Alterações não salvas." below is the on-screen half; this guards a page leave.
  useBeforeUnloadGuard(dirty);
  const readOnly = !canEdit;

  const onSave = () => {
    save.mutate(
      { accountId, overrides: draft },
      { onSuccess: () => toast.success("Configuração do SIMEC salva.") },
    );
  };

  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <section key={section.key} className="space-y-2" data-testid={`simec-cfg-section-${section.key}`}>
          <h3 className="text-sm font-semibold">{section.title}</h3>
          <div className="divide-y rounded-md border">
            {section.items.map((item) => {
              const paths = item.fields.map((f) => f.path);
              const overridden = hasAnyPath(draft, paths);
              return (
                <div key={item.id} className="flex flex-wrap items-end gap-4 p-3" data-testid={`simec-cfg-item-${item.id}`}>
                  <div className="min-w-[12rem] flex-1">
                    <div className="text-sm font-medium">{item.title}</div>
                    {overridden && (
                      <Badge variant="secondary" className="mt-1" data-testid={`simec-cfg-overridden-${item.id}`}>
                        personalizado
                      </Badge>
                    )}
                  </div>
                  {item.fields.map((f) => (
                    <FieldInput
                      key={f.path.join(".")}
                      field={f}
                      value={getPath(draft, f.path) ?? getPath(base, f.path)}
                      disabled={readOnly}
                      onChange={(v) => setDraft((d) => applyFieldEdit(d, base, f.path, v))}
                    />
                  ))}
                  {canEdit && overridden && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      title={restoreHint}
                      onClick={() => setDraft((d) => restoreItem(d, paths))}
                      data-testid={`simec-cfg-restore-${item.id}`}
                    >
                      <RotateCcw className="mr-1 h-3.5 w-3.5" />
                      Restaurar padrão
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {canEdit && (
        <div className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t bg-background py-3">
          <FormError message={save.isError ? simecErrorMessage(save.error, "config") : null} />
          <span className="text-xs text-muted-foreground">
            {dirty ? "Alterações não salvas." : "Sem alterações."}
          </span>
          <div className="ml-auto flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={Object.keys(draft).length === 0}
              onClick={() => setDraft({})}
              title={restoreHint}
              data-testid="simec-cfg-restore-all"
            >
              Restaurar tudo
            </Button>
            <Button type="button" size="sm" disabled={!dirty || save.isPending} onClick={onSave} data-testid="simec-cfg-save">
              <Save className="mr-1 h-3.5 w-3.5" />
              {save.isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Editor shell (layer choice + data) ─────────────────────────────────────

type LayerKind = "org" | "perfil";

export function SimecConfigEditor({
  accountId,
  accountName,
  canEdit,
}: {
  accountId: string | null;
  accountName: string | null;
  canEdit: boolean;
}) {
  const [kind, setKind] = useState<LayerKind>("org");
  const layerKind: LayerKind = accountId ? kind : "org";
  const defaultsQ = useSimecDefaults();
  const orgQ = useSimecConfig(null);
  const acctQ = useSimecConfig(accountId);

  const isOrg = layerKind === "org";
  const baseQ = isOrg ? defaultsQ : orgQ;
  const layerQ = isOrg ? orgQ : acctQ;
  const base = baseQ.data?.config;
  const layerResp = layerQ.data;
  const layer = isOrg ? (layerResp?.layers.org ?? null) : (layerResp?.layers.account ?? null);
  // A placeholder (previous profile's) config must never be edited as this one's.
  const waiting = baseQ.showSkeleton || layerQ.showSkeleton || layerQ.isPlaceholderData;
  const error = baseQ.error ?? layerQ.error;

  return (
    <Card data-testid="simec-config-editor">
      <CardHeader className="space-y-2">
        <CardTitle className="text-base">Configuração do SIMEC</CardTitle>
        <p className="text-sm text-muted-foreground">
          Janelas, indicadores, linha de base, alertas e cadência. Nada é fixo no código: o padrão
          recomendado vem do SIMEC, a organização pode ajustá-lo e cada perfil pode ter ajustes próprios.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant={isOrg ? "default" : "outline"}
            onClick={() => setKind("org")}
            data-testid="simec-cfg-layer-org"
          >
            Organização
          </Button>
          <Button
            type="button"
            size="sm"
            variant={!isOrg ? "default" : "outline"}
            disabled={!accountId}
            onClick={() => setKind("perfil")}
            data-testid="simec-cfg-layer-perfil"
            title={accountId ? undefined : "Conecte um perfil do Instagram para ajustes por perfil."}
          >
            Perfil{accountName ? ` ${accountName}` : ""}
          </Button>
          {layerResp && !waiting && (
            <span className="text-xs text-muted-foreground" data-testid="simec-cfg-version" title={`fingerprint ${layerResp.fingerprint}`}>
              Versão efetiva: {layerResp.version}
              {layer ? ` · camada v${layer.version}` : " · camada sem ajustes"}
            </span>
          )}
        </div>
        {!canEdit && (
          <p className="text-xs text-muted-foreground" data-testid="simec-cfg-readonly">
            Somente proprietários e administradores podem alterar a configuração do SIMEC.
          </p>
        )}
      </CardHeader>
      <CardContent>
        {error && !base ? (
          <ErrorState message={simecErrorMessage(error, "config")} />
        ) : waiting || !base ? (
          <div className="space-y-2" data-testid="simec-cfg-skeleton">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-2/3" />
          </div>
        ) : (
          <LayerForm
            key={`${layerKind}:${accountId ?? ""}:${layer?.version ?? 0}`}
            base={base}
            layer={layer}
            accountId={isOrg ? null : accountId}
            canEdit={canEdit}
            restoreHint={
              isOrg ? "Volta ao padrão recomendado do SIMEC." : "Volta ao valor definido para a organização."
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

export default SimecConfigEditor;
