/**
 * `<ImovelAvaliacaoSection/>` — "Características para avaliação" (migration 264).
 *
 * The inputs the price evaluator (NBR 14653 comparables + IBAPE-SP
 * homogenization) needs and Vista does not carry: building standard
 * (padrão IBAPE), conservation (Ross-Heidecke) and lot attributes. Filled by
 * brokers on the imóvel; the areas here are authored overrides — the Vista
 * mirror is never written. Lot fields apply to terreno/casa, not apartamento.
 */
import { useEffect, useState } from "react";
import { Loader2, Pencil, Ruler } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

import type { ImovelDados, ImovelDadosPatch } from "@/hooks/useImovelDados";
import { UnsavedChangesNotice, useUnsavedChanges } from "@noctusai/lib/components";

export const PADRAO_OPCOES = [
  { value: "simples", label: "Simples", help: "Acabamento econômico, materiais básicos, sem áreas de lazer." },
  { value: "medio", label: "Médio", help: "Acabamento corrente, projeto convencional." },
  { value: "superior", label: "Superior", help: "Bom acabamento, materiais selecionados, algum lazer." },
  { value: "fino", label: "Fino", help: "Acabamento esmerado, projeto diferenciado." },
  { value: "luxo", label: "Luxo", help: "Acabamento e projeto de alto requinte, materiais nobres." },
] as const;

export const CONSERVACAO_OPCOES = [
  { value: "novo", label: "Novo" },
  { value: "entre_novo_e_regular", label: "Entre novo e regular" },
  { value: "regular", label: "Regular" },
  { value: "reparos_simples", label: "Necessita de reparos simples" },
  { value: "reparos_importantes", label: "Necessita de reparos importantes" },
  { value: "sem_valor", label: "Sem valor (demolição)" },
] as const;

export const TOPOGRAFIA_OPCOES = [
  { value: "plano", label: "Plano" },
  { value: "aclive_leve", label: "Aclive leve" },
  { value: "aclive_acentuado", label: "Aclive acentuado" },
  { value: "declive_leve", label: "Declive leve" },
  { value: "declive_acentuado", label: "Declive acentuado" },
  { value: "irregular", label: "Irregular" },
] as const;

export const POSICAO_OPCOES = [
  { value: "meio_quadra", label: "Meio de quadra" },
  { value: "esquina", label: "Esquina" },
  { value: "multiplas_frentes", label: "Múltiplas frentes" },
] as const;

/** Lot attributes are meaningless for a unit in a building. Unknown/blank
 *  categoria shows them (do not hide inputs on missing data). */
export function mostraLote(categoria: string | null | undefined): boolean {
  if (!categoria) return true;
  return !/apartamento|flat|kitnet|studio|loft|cobertura/i.test(categoria);
}

interface Props {
  dados: ImovelDados | undefined;
  categoria: string | null | undefined;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onSave: (patch: ImovelDadosPatch) => void;
}

interface Draft {
  padrao_construtivo: string;
  estado_conservacao: string;
  area_terreno_m2: string;
  area_construida_m2: string;
  testada_m: string;
  profundidade_m: string;
  topografia: string;
  posicao_lote: string;
}

const num = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));

function toDraft(d: ImovelDados | undefined): Draft {
  return {
    padrao_construtivo: d?.padrao_construtivo ?? "",
    estado_conservacao: d?.estado_conservacao ?? "",
    area_terreno_m2: num(d?.area_terreno_m2),
    area_construida_m2: num(d?.area_construida_m2),
    testada_m: num(d?.testada_m),
    profundidade_m: num(d?.profundidade_m),
    topografia: d?.topografia ?? "",
    posicao_lote: d?.posicao_lote ?? "",
  };
}

const labelDe = (opcoes: readonly { value: string; label: string }[], v: string | null | undefined) =>
  opcoes.find((o) => o.value === v)?.label ?? null;

const fmtNum = (v: number | null | undefined, un: string) =>
  v === null || v === undefined ? null : `${v.toLocaleString("pt-BR")} ${un}`;

function parseNum(s: string): number | null {
  const t = s.trim().replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n > 0 ? n : NaN;
}

function Linha({ label, value, testid }: { label: string; value: string | null; testid: string }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm" data-testid={testid}>
        {value ?? <span className="text-muted-foreground">Não informado</span>}
      </dd>
    </div>
  );
}

function CampoSelect({
  id,
  label,
  value,
  onChange,
  opcoes,
  help,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  opcoes: readonly { value: string; label: string }[];
  help?: string;
  disabled: boolean;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <select
        id={id}
        data-testid={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
      >
        <option value="">Não informado</option>
        {opcoes.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {help && <p className="text-xs text-muted-foreground">{help}</p>}
    </div>
  );
}

export default function ImovelAvaliacaoSection({ dados, categoria, loading, saving, error, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => toDraft(dados));
  const [invalid, setInvalid] = useState<string | null>(null);
  const [wasSaving, setWasSaving] = useState(false);
  const lote = mostraLote(categoria);

  useEffect(() => {
    if (!editing) setDraft(toDraft(dados));
  }, [
    editing,
    dados?.padrao_construtivo,
    dados?.estado_conservacao,
    dados?.area_terreno_m2,
    dados?.area_construida_m2,
    dados?.testada_m,
    dados?.profundidade_m,
    dados?.topografia,
    dados?.posicao_lote,
  ]);

  // Leave edit mode once a save finishes without error.
  useEffect(() => {
    if (wasSaving && !saving && !error) setEditing(false);
    setWasSaving(saving);
  }, [saving]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k: keyof Draft) => (v: string) => setDraft((d) => ({ ...d, [k]: v }));
  // While editing, a typed value is not saved until "Salvar": say so (F91 class).
  const { dirty } = useUnsavedChanges(draft, editing && dados ? toDraft(dados) : undefined);
  const showSkeleton = loading;

  function submit() {
    const nums = {
      area_terreno_m2: parseNum(draft.area_terreno_m2),
      area_construida_m2: parseNum(draft.area_construida_m2),
      testada_m: parseNum(draft.testada_m),
      profundidade_m: parseNum(draft.profundidade_m),
    };
    if (Object.values(nums).some((n) => Number.isNaN(n))) {
      setInvalid("Informe medidas maiores que zero (use ponto ou vírgula).");
      return;
    }
    setInvalid(null);
    const enumOuNull = <T extends string>(v: string) => (v === "" ? null : (v as T));
    const patch: ImovelDadosPatch = {
      padrao_construtivo: enumOuNull(draft.padrao_construtivo),
      estado_conservacao: enumOuNull(draft.estado_conservacao),
      area_terreno_m2: nums.area_terreno_m2,
      area_construida_m2: nums.area_construida_m2,
    };
    if (lote) {
      patch.testada_m = nums.testada_m;
      patch.profundidade_m = nums.profundidade_m;
      patch.topografia = enumOuNull(draft.topografia);
      patch.posicao_lote = enumOuNull(draft.posicao_lote);
    }
    onSave(patch);
  }

  const por = dados?.avaliacao_campos_atualizado_por?.nome ?? null;
  const em = dados?.avaliacao_campos_atualizado_em;
  const quando = em ? new Date(em).toLocaleDateString("pt-BR") : null;

  return (
    <Card data-testid="imovel-avaliacao">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Ruler className="h-4 w-4" />
          Características para avaliação
        </CardTitle>
        {!editing && !showSkeleton && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setEditing(true)}
            data-testid="imovel-avaliacao-editar"
          >
            <Pencil className="mr-1 h-3.5 w-3.5" />
            Editar
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {showSkeleton ? (
          <div data-testid="imovel-avaliacao-skeleton">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : !dados ? (
          <p className="text-sm text-destructive" role="alert" data-testid="imovel-avaliacao-erro">
            Não foi possível carregar as características para avaliação.
          </p>
        ) : editing ? (
          <>
            <p className="text-xs text-muted-foreground">
              Usadas pelo avaliador de preço (NBR 14653 / IBAPE-SP). As áreas aqui são
              informadas por nós e não alteram os dados do CRM.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <CampoSelect
                id="avaliacao-padrao"
                label="Padrão construtivo (IBAPE)"
                value={draft.padrao_construtivo}
                onChange={set("padrao_construtivo")}
                opcoes={PADRAO_OPCOES}
                help={PADRAO_OPCOES.find((o) => o.value === draft.padrao_construtivo)?.help ??
                  "Escala IBAPE-SP: simples, médio, superior, fino, luxo."}
                disabled={saving}
              />
              <CampoSelect
                id="avaliacao-conservacao"
                label="Estado de conservação"
                value={draft.estado_conservacao}
                onChange={set("estado_conservacao")}
                opcoes={CONSERVACAO_OPCOES}
                help="Escala de Ross-Heidecke usada com o IBAPE."
                disabled={saving}
              />
              {(
                [
                  ["area_terreno_m2", "Área do terreno (m²)"],
                  ["area_construida_m2", "Área construída (m²)"],
                  ...(lote
                    ? ([
                        ["testada_m", "Testada / frente (m)"],
                        ["profundidade_m", "Profundidade (m)"],
                      ] as const)
                    : []),
                ] as const
              ).map(([k, rotulo]) => (
                <div key={k} className="space-y-1">
                  <Label htmlFor={`avaliacao-${k}`} className="text-xs">
                    {rotulo}
                  </Label>
                  <Input
                    id={`avaliacao-${k}`}
                    data-testid={`avaliacao-${k}`}
                    inputMode="decimal"
                    value={draft[k]}
                    onChange={(e) => set(k)(e.target.value)}
                    disabled={saving}
                  />
                </div>
              ))}
              {lote && (
                <>
                  <CampoSelect
                    id="avaliacao-topografia"
                    label="Topografia"
                    value={draft.topografia}
                    onChange={set("topografia")}
                    opcoes={TOPOGRAFIA_OPCOES}
                    disabled={saving}
                  />
                  <CampoSelect
                    id="avaliacao-posicao"
                    label="Posição na quadra"
                    value={draft.posicao_lote}
                    onChange={set("posicao_lote")}
                    opcoes={POSICAO_OPCOES}
                    disabled={saving}
                  />
                </>
              )}
            </div>
            {(invalid || error) && (
              <p className="text-sm text-destructive" role="alert" data-testid="imovel-avaliacao-msg-erro">
                {invalid ?? error}
              </p>
            )}
            <UnsavedChangesNotice dirty={dirty} data-testid="imovel-avaliacao-nao-salvo" />
            <div className="flex gap-2">
              <Button type="button" size="sm" onClick={submit} disabled={saving} data-testid="imovel-avaliacao-salvar">
                {saving && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                Salvar
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={saving}
                onClick={() => {
                  setDraft(toDraft(dados));
                  setInvalid(null);
                  setEditing(false);
                }}
              >
                Cancelar
              </Button>
            </div>
          </>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Linha label="Padrão construtivo (IBAPE)" value={labelDe(PADRAO_OPCOES, dados.padrao_construtivo)} testid="v-padrao" />
              <Linha label="Estado de conservação" value={labelDe(CONSERVACAO_OPCOES, dados.estado_conservacao)} testid="v-conservacao" />
              <Linha label="Área do terreno" value={fmtNum(dados.area_terreno_m2, "m²")} testid="v-area-terreno" />
              <Linha label="Área construída" value={fmtNum(dados.area_construida_m2, "m²")} testid="v-area-construida" />
              {lote && (
                <>
                  <Linha label="Testada" value={fmtNum(dados.testada_m, "m")} testid="v-testada" />
                  <Linha label="Profundidade" value={fmtNum(dados.profundidade_m, "m")} testid="v-profundidade" />
                  <Linha label="Topografia" value={labelDe(TOPOGRAFIA_OPCOES, dados.topografia)} testid="v-topografia" />
                  <Linha label="Posição na quadra" value={labelDe(POSICAO_OPCOES, dados.posicao_lote)} testid="v-posicao" />
                </>
              )}
            </dl>
            {quando ? (
              <p className="text-xs text-muted-foreground" data-testid="imovel-avaliacao-autoria">
                Preenchido por {por ?? "usuário não identificado"} em {quando}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground" data-testid="imovel-avaliacao-vazio">
                Ainda não preenchido. Estes dados alimentam o avaliador de preço.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
