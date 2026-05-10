/**
 * SelloutReportSubmit — Phase 7 SKELETON.
 *
 * Three-mode submission per PROJECT.md §6 Phase 4:
 *   1. structured form     — line items typed in by hand
 *   2. NF-e XML upload     — single XML file dropped, parsed server-side
 *   3. freeform attachment — arbitrary file (PDF/XLSX/etc.) + notes
 *
 * Uses react-hook-form for the structured form. Mode-switcher tabs let
 * the distributor pick a submission path.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm, useFieldArray } from "react-hook-form";
import { FileText, Plus, Trash2, Upload } from "lucide-react";
import { useSubmitSellout } from "@/hooks/useSellout";
import type { SelloutLineItem, SelloutSubmissionMode } from "@/types";

const inputClass =
  "w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

interface StructuredFormData {
  period_month: string;
  line_items: SelloutLineItem[];
}

export default function SelloutReportSubmit() {
  const navigate = useNavigate();
  const { submit, isPending } = useSubmitSellout();
  const [mode, setMode] = useState<SelloutSubmissionMode>("structured");

  // Structured form
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<StructuredFormData>({
    defaultValues: {
      period_month: new Date().toISOString().slice(0, 7),
      line_items: [{ product_sku: "", quantity: 0, unit_price: 0 }],
    },
  });
  const { fields, append, remove } = useFieldArray({
    control,
    name: "line_items",
  });

  // NF-e XML upload state
  const [nfeFile, setNfeFile] = useState<File | null>(null);
  const [nfeMonth, setNfeMonth] = useState(new Date().toISOString().slice(0, 7));

  // Freeform upload state
  const [freeformFile, setFreeformFile] = useState<File | null>(null);
  const [freeformMonth, setFreeformMonth] = useState(
    new Date().toISOString().slice(0, 7)
  );
  const [freeformNotes, setFreeformNotes] = useState("");

  const onStructuredSubmit = (data: StructuredFormData) => {
    submit({
      submission_mode: "structured",
      period_month: data.period_month,
      line_items: data.line_items,
    });
    navigate("/sellout");
  };

  const onNfeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!nfeFile) return;
    submit({
      submission_mode: "nfe_xml",
      period_month: nfeMonth,
      nfe_file: nfeFile,
    });
    navigate("/sellout");
  };

  const onFreeformSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!freeformFile) return;
    submit({
      submission_mode: "freeform",
      period_month: freeformMonth,
      attachment_file: freeformFile,
      notes: freeformNotes,
    });
    navigate("/sellout");
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Enviar relatório de sellout</h1>
          <p className="text-sm text-muted-foreground">
            Escolha o modo de envio mais conveniente para o seu fluxo
          </p>
        </div>
      </div>

      {/* Mode switcher */}
      <div className="flex gap-2 border-b border-border">
        {(
          [
            { key: "structured" as const, label: "Formulário" },
            { key: "nfe_xml" as const, label: "Upload NF-e (XML)" },
            { key: "freeform" as const, label: "Anexo livre" },
          ]
        ).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setMode(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === tab.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {mode === "structured" && (
        <form
          onSubmit={handleSubmit(onStructuredSubmit)}
          className="rounded-lg border border-border bg-card p-5 space-y-4"
        >
          <div className="space-y-1 max-w-xs">
            <label className="text-sm font-medium text-foreground">Mês de referência</label>
            <input
              type="month"
              className={inputClass}
              {...register("period_month", { required: "Obrigatório" })}
            />
            {errors.period_month && (
              <p className="text-xs text-destructive">{errors.period_month.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Itens</label>
            {fields.map((field, idx) => (
              <div key={field.id} className="grid gap-2 grid-cols-12 items-start">
                <input
                  type="text"
                  placeholder="SKU"
                  className={`${inputClass} col-span-5`}
                  {...register(`line_items.${idx}.product_sku` as const)}
                />
                <input
                  type="number"
                  placeholder="Qtd."
                  className={`${inputClass} col-span-3`}
                  {...register(`line_items.${idx}.quantity` as const, {
                    valueAsNumber: true,
                  })}
                />
                <input
                  type="number"
                  step="0.01"
                  placeholder="Preço unit."
                  className={`${inputClass} col-span-3`}
                  {...register(`line_items.${idx}.unit_price` as const, {
                    valueAsNumber: true,
                  })}
                />
                <button
                  type="button"
                  onClick={() => remove(idx)}
                  className="col-span-1 p-2 rounded-md hover:bg-destructive/10 text-destructive"
                  title="Remover item"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => append({ product_sku: "", quantity: 0, unit_price: 0 })}
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              <Plus className="h-4 w-4" /> Adicionar item
            </button>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isPending}
              className="px-6 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isPending ? "Enviando…" : "Enviar relatório"}
            </button>
          </div>
        </form>
      )}

      {mode === "nfe_xml" && (
        <form
          onSubmit={onNfeSubmit}
          className="rounded-lg border border-border bg-card p-5 space-y-4"
        >
          <div className="space-y-1 max-w-xs">
            <label className="text-sm font-medium text-foreground">Mês de referência</label>
            <input
              type="month"
              className={inputClass}
              value={nfeMonth}
              onChange={(e) => setNfeMonth(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">
              Arquivo NF-e (XML)
            </label>
            <div className="flex items-center gap-3">
              <input
                type="file"
                accept=".xml,application/xml,text/xml"
                onChange={(e) => setNfeFile(e.target.files?.[0] ?? null)}
                className={inputClass}
                required
              />
              <Upload className="h-4 w-4 text-muted-foreground" />
            </div>
            {nfeFile && (
              <p className="text-xs text-muted-foreground">
                Selecionado: {nfeFile.name}
              </p>
            )}
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isPending || !nfeFile}
              className="px-6 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isPending ? "Enviando…" : "Enviar NF-e"}
            </button>
          </div>
        </form>
      )}

      {mode === "freeform" && (
        <form
          onSubmit={onFreeformSubmit}
          className="rounded-lg border border-border bg-card p-5 space-y-4"
        >
          <div className="space-y-1 max-w-xs">
            <label className="text-sm font-medium text-foreground">Mês de referência</label>
            <input
              type="month"
              className={inputClass}
              value={freeformMonth}
              onChange={(e) => setFreeformMonth(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Anexo</label>
            <input
              type="file"
              onChange={(e) => setFreeformFile(e.target.files?.[0] ?? null)}
              className={inputClass}
              required
            />
            {freeformFile && (
              <p className="text-xs text-muted-foreground">
                Selecionado: {freeformFile.name}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Observações</label>
            <textarea
              rows={3}
              className={inputClass}
              value={freeformNotes}
              onChange={(e) => setFreeformNotes(e.target.value)}
            />
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isPending || !freeformFile}
              className="px-6 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isPending ? "Enviando…" : "Enviar anexo"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
