/** Manual plan creation + item add/edit dialogs. */
import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { ClientSelect } from "@/components/ClientSelect";
import {
  useCreatePlan,
  useAppendPlanItems,
  useUpdatePlanItem,
  type ContentPlan,
  type PlanItem,
  type PlanItemInput,
} from "@/hooks/useContentPlans";
import type { Platform, Campaign } from "@/hooks/useConteudo";
import {
  BTN_OUTLINE,
  BTN_PRIMARY,
  Field,
  FORMAT_OPTIONS,
  INPUT_CLS,
  Modal,
  PLATFORM_OPTIONS,
  TEXTAREA_CLS,
} from "./PlanUi";

// ---------------------------------------------------------------------------
// Item form (shared by "add" and "edit")
// ---------------------------------------------------------------------------

interface ItemForm {
  title: string;
  description: string;
  format: string;
  platform: Platform | "";
  post_date: string;
  due_date: string;
  caption: string;
  reference_notes: string;
}

const EMPTY_ITEM: ItemForm = {
  title: "", description: "", format: "", platform: "", post_date: "", due_date: "", caption: "", reference_notes: "",
};

function toForm(item: PlanItem | null): ItemForm {
  if (!item) return EMPTY_ITEM;
  return {
    title: item.title,
    description: item.description ?? "",
    format: item.format ?? "",
    platform: item.platform ?? "",
    post_date: item.post_date ?? "",
    due_date: item.due_date ?? "",
    caption: item.caption ?? "",
    reference_notes: item.reference_notes ?? "",
  };
}

/** Empty strings are dropped (the API treats absent as "no value"). */
function formToInput(f: ItemForm): PlanItemInput {
  const out: PlanItemInput = { title: f.title.trim() };
  if (f.description.trim()) out.description = f.description.trim();
  if (f.format) out.format = f.format;
  if (f.platform) out.platform = f.platform;
  if (f.post_date) out.post_date = f.post_date;
  if (f.due_date) out.due_date = f.due_date;
  if (f.caption.trim()) out.caption = f.caption.trim();
  if (f.reference_notes.trim()) out.reference_notes = f.reference_notes.trim();
  return out;
}

function ItemFields({
  form,
  setForm,
  idPrefix,
}: {
  form: ItemForm;
  setForm: (f: ItemForm) => void;
  idPrefix: string;
}) {
  const set = <K extends keyof ItemForm>(k: K, v: ItemForm[K]) => setForm({ ...form, [k]: v });
  return (
    <div className="space-y-3">
      <Field label="Título *" htmlFor={`${idPrefix}-title`}>
        <input id={`${idPrefix}-title`} required className={INPUT_CLS} value={form.title}
          onChange={(e) => set("title", e.target.value)} placeholder="Ex: Reels de bastidores" />
      </Field>
      <Field label="Descrição / instruções" htmlFor={`${idPrefix}-desc`}>
        <textarea id={`${idPrefix}-desc`} rows={3} className={TEXTAREA_CLS} value={form.description}
          onChange={(e) => set("description", e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Formato" htmlFor={`${idPrefix}-format`}>
          <input id={`${idPrefix}-format`} list={`${idPrefix}-formats`} className={INPUT_CLS} value={form.format}
            onChange={(e) => set("format", e.target.value)} />
          <datalist id={`${idPrefix}-formats`}>
            {FORMAT_OPTIONS.map((f) => <option key={f} value={f} />)}
          </datalist>
        </Field>
        <Field label="Plataforma" htmlFor={`${idPrefix}-platform`}>
          <select id={`${idPrefix}-platform`} className={INPUT_CLS} value={form.platform}
            onChange={(e) => set("platform", e.target.value as Platform | "")}>
            <option value="">—</option>
            {PLATFORM_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </Field>
        <Field label="Data de publicação" htmlFor={`${idPrefix}-post`}>
          <input id={`${idPrefix}-post`} type="date" className={INPUT_CLS} value={form.post_date}
            onChange={(e) => set("post_date", e.target.value)} />
        </Field>
        <Field label="Prazo da tarefa" htmlFor={`${idPrefix}-due`}>
          <input id={`${idPrefix}-due`} type="date" className={INPUT_CLS} value={form.due_date}
            onChange={(e) => set("due_date", e.target.value)} />
        </Field>
      </div>
      <Field label="Legenda sugerida" htmlFor={`${idPrefix}-caption`}>
        <textarea id={`${idPrefix}-caption`} rows={2} className={TEXTAREA_CLS} value={form.caption}
          onChange={(e) => set("caption", e.target.value)} />
      </Field>
      <Field label="Referências" htmlFor={`${idPrefix}-refs`}>
        <textarea id={`${idPrefix}-refs`} rows={2} className={TEXTAREA_CLS} value={form.reference_notes}
          onChange={(e) => set("reference_notes", e.target.value)} placeholder="Links, perfis, inspirações" />
      </Field>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add / edit one item
// ---------------------------------------------------------------------------

export function ItemDialog({
  plan,
  editing,
  onClose,
}: {
  plan: ContentPlan;
  editing: PlanItem | null;
  onClose: () => void;
}) {
  const append = useAppendPlanItems();
  const update = useUpdatePlanItem();
  const [form, setForm] = useState<ItemForm>(() => toForm(editing));
  const pending = append.isPending || update.isPending;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) return;
    if (editing) {
      // Edit sends every field so cleared values are not silently kept.
      update.mutate(
        {
          planId: plan.id,
          itemId: editing.id,
          title: form.title.trim(),
          description: form.description.trim(),
          format: form.format,
          platform: form.platform || undefined,
          post_date: form.post_date || undefined,
          due_date: form.due_date || undefined,
          caption: form.caption.trim(),
          reference_notes: form.reference_notes.trim(),
        },
        { onSuccess: onClose },
      );
    } else {
      append.mutate({ planId: plan.id, items: [formToInput(form)] }, { onSuccess: onClose });
    }
  }

  return (
    <Modal title={editing ? "Editar conteúdo" : "Novo conteúdo"} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-4">
        <ItemFields form={form} setForm={setForm} idPrefix="planitem" />
        <div className="flex justify-end gap-3 pt-1">
          <button type="button" onClick={onClose} className={BTN_OUTLINE}>Cancelar</button>
          <button type="submit" disabled={pending || !form.title.trim()} className={BTN_PRIMARY}>
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            {editing ? "Salvar" : "Adicionar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Create a plan manually (optional first items)
// ---------------------------------------------------------------------------

export function ManualPlanDialog({
  campaigns,
  onClose,
  onCreated,
}: {
  campaigns: Campaign[];
  onClose: () => void;
  onCreated: (plan: ContentPlan) => void;
}) {
  const create = useCreatePlan();
  const [title, setTitle] = useState("");
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [clientId, setClientId] = useState<string | undefined>(undefined);
  const [campaignId, setCampaignId] = useState("");
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState<string[]>([]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    create.mutate(
      {
        title: title.trim(),
        month,
        client_id: clientId,
        campaign_id: campaignId || undefined,
        strategy_context: notes.trim() ? { notes: notes.trim() } : {},
        creation_mode: "manual",
        items: rows.map((r) => r.trim()).filter(Boolean).map((t) => ({ title: t })),
      },
      { onSuccess: (plan) => onCreated(plan) },
    );
  }

  return (
    <Modal title="Novo planejamento" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Título *" htmlFor="plan-title">
          <input id="plan-title" required className={INPUT_CLS} value={title}
            onChange={(e) => setTitle(e.target.value)} placeholder="Ex: Planejamento de Novembro" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Mês *" htmlFor="plan-month">
            <input id="plan-month" type="month" required className={INPUT_CLS} value={month}
              onChange={(e) => setMonth(e.target.value)} />
          </Field>
          <Field label="Campanha" htmlFor="plan-campaign">
            <select id="plan-campaign" className={INPUT_CLS} value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}>
              <option value="">Sem campanha</option>
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        </div>
        <ClientSelect value={clientId} onChange={setClientId} id="plan-client" />
        <Field label="Estratégia / observações" htmlFor="plan-notes">
          <textarea id="plan-notes" rows={2} className={TEXTAREA_CLS} value={notes}
            onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <div>
          <p className="mb-1 text-sm font-medium text-foreground">Conteúdos iniciais (opcional)</p>
          <div className="space-y-2">
            {rows.map((r, i) => (
              <div key={i} className="flex gap-2">
                <input aria-label={`Conteúdo ${i + 1}`} className={INPUT_CLS} value={r} placeholder="Título do conteúdo"
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? e.target.value : x)))} />
                <button type="button" aria-label="Remover linha" onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  className="rounded-md p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => setRows([...rows, ""])}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
              <Plus className="h-3.5 w-3.5" /> Adicionar conteúdo
            </button>
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-1">
          <button type="button" onClick={onClose} className={BTN_OUTLINE}>Cancelar</button>
          <button type="submit" disabled={create.isPending || !title.trim()} className={BTN_PRIMARY}>
            {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Criar planejamento
          </button>
        </div>
      </form>
    </Modal>
  );
}
