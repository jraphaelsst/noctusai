/**
 * AI generation of plan items: briefing form -> preview with checkboxes ->
 * append the selected ones as "planned". The backend validates the model
 * output strictly and answers an honest 503 when AI is not configured; that
 * message is shown inline (never a fake preview).
 */
import { useState } from "react";
import { ArrowLeft, Loader2, Sparkles } from "lucide-react";
import {
  useAppendPlanItems,
  useGenerateAIItems,
  type AIGenerateParams,
  type AIGeneratedItem,
  type ContentPlan,
} from "@/hooks/useContentPlans";
import type { Platform } from "@/hooks/useConteudo";
import {
  BTN_OUTLINE,
  BTN_PRIMARY,
  Field,
  FORMAT_OPTIONS,
  fmtDay,
  INPUT_CLS,
  Modal,
  PLATFORM_LABEL,
  PLATFORM_OPTIONS,
  TEXTAREA_CLS,
} from "./PlanUi";

const WEEKDAYS = [
  { value: 1, label: "Seg" }, { value: 2, label: "Ter" }, { value: 3, label: "Qua" },
  { value: 4, label: "Qui" }, { value: 5, label: "Sex" }, { value: 6, label: "Sáb" },
  { value: 0, label: "Dom" },
];
const OBJECTIVES = ["Autoridade", "Engajamento", "Vendas / Conversão", "Educacional", "Lançamento", "Institucional", "Misto"];
const TONES = ["Profissional", "Descontraído", "Inspirador", "Técnico", "Divertido", "Outro"];
const PERIODS = [7, 14, 30, 60, 90] as const;

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function AIGenerateDialog({ plan, onClose }: { plan: ContentPlan; onClose: () => void }) {
  const generate = useGenerateAIItems();
  const append = useAppendPlanItems();

  const [itemsCount, setItemsCount] = useState(4);
  const [periodDays, setPeriodDays] = useState<AIGenerateParams["period_days"]>(30);
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [weekdays, setWeekdays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [platforms, setPlatforms] = useState<Platform[]>(["instagram"]);
  const [formats, setFormats] = useState<string[]>([]);
  const [focus, setFocus] = useState("");
  const [objective, setObjective] = useState("");
  const [tone, setTone] = useState("");
  const [toneCustom, setToneCustom] = useState("");
  const [audience, setAudience] = useState("");
  const [pillars, setPillars] = useState("");
  const [mix, setMix] = useState("");
  const [allowSalesCta, setAllowSalesCta] = useState(true);
  const [avoid, setAvoid] = useState("");
  const [references, setReferences] = useState("");

  const [preview, setPreview] = useState<AIGeneratedItem[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const canGenerate = platforms.length > 0 && weekdays.length > 0 && !generate.isPending;

  function submit() {
    const params: AIGenerateParams = {
      items_count: itemsCount,
      period_days: periodDays,
      start_date: startDate,
      weekdays,
      platforms,
      formats,
      focus: focus.trim() || undefined,
      objective: objective || undefined,
      tone: tone || undefined,
      tone_custom: tone === "Outro" && toneCustom.trim() ? toneCustom.trim() : undefined,
      audience: audience.trim() || undefined,
      pillars: pillars.split(",").map((p) => p.trim()).filter(Boolean),
      mix_distribution: mix.trim() || undefined,
      allow_sales_cta: allowSalesCta,
      avoid: avoid.trim() || undefined,
      references: references.trim() || undefined,
    };
    generate.mutate(
      { planId: plan.id, params },
      {
        onSuccess: (res) => {
          setPreview(res.items);
          setSelected(new Set(res.items.map((_, i) => i)));
        },
      },
    );
  }

  function confirm() {
    if (!preview) return;
    const chosen = preview.filter((_, i) => selected.has(i));
    if (chosen.length === 0) return;
    append.mutate(
      {
        planId: plan.id,
        items: chosen.map((c) => ({
          title: c.title,
          description: c.description ?? undefined,
          format: c.format ?? undefined,
          platform: c.platform,
          post_date: c.post_date,
          reference_notes: c.reference_notes ?? undefined,
        })),
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal title="Gerar conteúdos com IA" onClose={onClose} wide>
      {preview === null ? (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Quanto mais contexto, melhor o resultado.</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Quantidade (1–20)" htmlFor="ai-count">
              <input id="ai-count" type="number" min={1} max={20} className={INPUT_CLS} value={itemsCount}
                onChange={(e) => setItemsCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
            </Field>
            <Field label="Distribuir nos próximos" htmlFor="ai-period">
              <select id="ai-period" className={INPUT_CLS} value={periodDays}
                onChange={(e) => setPeriodDays(Number(e.target.value) as AIGenerateParams["period_days"])}>
                {PERIODS.map((d) => <option key={d} value={d}>{d} dias</option>)}
              </select>
            </Field>
            <Field label="Data de início" htmlFor="ai-start">
              <input id="ai-start" type="date" className={INPUT_CLS} value={startDate}
                onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <div>
              <p className="mb-1 text-sm font-medium text-foreground">Dias permitidos</p>
              <div className="flex flex-wrap gap-1.5">
                {WEEKDAYS.map((d) => (
                  <button key={d.value} type="button" aria-pressed={weekdays.includes(d.value)}
                    onClick={() => setWeekdays(toggle(weekdays, d.value))}
                    className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      weekdays.includes(d.value) ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
                    }`}>
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <fieldset>
            <legend className="mb-1 text-sm font-medium text-foreground">Plataformas</legend>
            <div className="flex flex-wrap gap-2">
              {PLATFORM_OPTIONS.map((p) => (
                <label key={p.value} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${
                  platforms.includes(p.value) ? "border-primary bg-primary/10 text-primary" : "bg-background"}`}>
                  <input type="checkbox" checked={platforms.includes(p.value)}
                    onChange={() => setPlatforms(toggle(platforms, p.value))} />
                  {p.label}
                </label>
              ))}
            </div>
          </fieldset>

          <Field label="Tema desta leva" htmlFor="ai-focus">
            <textarea id="ai-focus" rows={2} className={TEXTAREA_CLS} value={focus}
              onChange={(e) => setFocus(e.target.value)} placeholder="Ex: campanha de Black Friday, lançamento do curso X" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Objetivo principal" htmlFor="ai-objective">
              <select id="ai-objective" className={INPUT_CLS} value={objective} onChange={(e) => setObjective(e.target.value)}>
                <option value="">—</option>
                {OBJECTIVES.map((o) => <option key={o}>{o}</option>)}
              </select>
            </Field>
            <Field label="Tom de voz" htmlFor="ai-tone">
              <select id="ai-tone" className={INPUT_CLS} value={tone} onChange={(e) => setTone(e.target.value)}>
                <option value="">—</option>
                {TONES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
          </div>
          {tone === "Outro" && (
            <input aria-label="Descreva o tom" className={INPUT_CLS} value={toneCustom}
              onChange={(e) => setToneCustom(e.target.value)} placeholder="Descreva o tom desejado" />
          )}
          <Field label="Público-alvo" htmlFor="ai-audience">
            <textarea id="ai-audience" rows={2} className={TEXTAREA_CLS} value={audience}
              onChange={(e) => setAudience(e.target.value)} />
          </Field>
          <Field label="Pilares (separe por vírgula)" htmlFor="ai-pillars">
            <input id="ai-pillars" className={INPUT_CLS} value={pillars} onChange={(e) => setPillars(e.target.value)}
              placeholder="bastidores, dicas, prova social, ofertas" />
          </Field>

          <fieldset>
            <legend className="mb-1 text-sm font-medium text-foreground">Formatos</legend>
            <div className="flex flex-wrap gap-2">
              {FORMAT_OPTIONS.map((f) => (
                <label key={f} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${
                  formats.includes(f) ? "border-primary bg-primary/10 text-primary" : "bg-background"}`}>
                  <input type="checkbox" checked={formats.includes(f)} onChange={() => setFormats(toggle(formats, f))} />
                  {f}
                </label>
              ))}
            </div>
          </fieldset>
          <Field label="Mix sugerido" htmlFor="ai-mix">
            <input id="ai-mix" className={INPUT_CLS} value={mix} onChange={(e) => setMix(e.target.value)}
              placeholder="Ex: 60% educativo, 30% vendas, 10% bastidores" />
          </Field>
          <label className="flex items-center justify-between rounded-md border p-3 text-sm">
            <span>
              <span className="font-medium">Permitir CTAs de venda direta</span>
              <span className="block text-xs text-muted-foreground">Desligado, a IA evita posts puramente comerciais.</span>
            </span>
            <input type="checkbox" aria-label="Permitir CTAs de venda direta" checked={allowSalesCta}
              onChange={(e) => setAllowSalesCta(e.target.checked)} />
          </label>
          <Field label="O que evitar" htmlFor="ai-avoid">
            <textarea id="ai-avoid" rows={2} className={TEXTAREA_CLS} value={avoid} onChange={(e) => setAvoid(e.target.value)} />
          </Field>
          <Field label="Referências" htmlFor="ai-refs">
            <textarea id="ai-refs" rows={2} className={TEXTAREA_CLS} value={references}
              onChange={(e) => setReferences(e.target.value)} />
          </Field>

          {generate.isError && (
            <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {generate.error.message}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className={BTN_OUTLINE}>Cancelar</button>
            <button type="button" disabled={!canGenerate} onClick={submit} className={BTN_PRIMARY}>
              {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Gerar
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {preview.length} conteúdos gerados. Selecione os que deseja adicionar.
          </p>
          {preview.map((item, i) => (
            <label key={i} className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 ${
              selected.has(i) ? "border-primary bg-primary/5" : "border-border"}`}>
              <input type="checkbox" className="mt-1" checked={selected.has(i)}
                onChange={() => setSelected(new Set(toggle([...selected], i)))} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{item.title}</span>
                {item.description && <span className="block text-xs text-muted-foreground">{item.description}</span>}
                <span className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                  {item.format && <span className="rounded bg-muted px-1.5 py-0.5">{item.format}</span>}
                  <span className="rounded border px-1.5 py-0.5">{PLATFORM_LABEL[item.platform] ?? item.platform}</span>
                  <span className="rounded border px-1.5 py-0.5">{fmtDay(item.post_date)}</span>
                </span>
              </span>
            </label>
          ))}
          <div className="flex justify-end gap-3 pt-1">
            <button type="button" className={BTN_OUTLINE} onClick={() => setPreview(null)} disabled={append.isPending}>
              <ArrowLeft className="h-4 w-4" /> Voltar
            </button>
            <button type="button" className={BTN_PRIMARY} disabled={append.isPending || selected.size === 0} onClick={confirm}>
              {append.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Adicionar{selected.size > 0 ? ` (${selected.size})` : ""}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
