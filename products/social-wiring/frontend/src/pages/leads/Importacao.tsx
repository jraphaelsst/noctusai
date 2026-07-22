/**
 * Importacao — Leads "Importação" subtab (§6 of leads-module-PROJECT.md).
 *
 * Drop (or pick) an `.xlsx` → preview the diff (incl. the unmapped-origens /
 * unmapped-corretores queues) → commit · batch history table. Preview never
 * writes; commit upserts (idempotent on the backend's `source_sheet` +
 * `source_row` key, §4).
 */
import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TableSkeleton } from "@noctusai/lib/design-system";
import {
  useLeadImportBatches,
  useLeadImportCommit,
  useLeadImportPreview,
} from "@/hooks/useLeadsImport";
import { describeError } from "./utils";

const STATUS_LABEL: Record<string, string> = { running: "Em andamento", ok: "OK", erro: "Erro" };
const STATUS_VARIANT: Record<string, "default" | "destructive" | "secondary"> = {
  running: "secondary",
  ok: "default",
  erro: "destructive",
};

export default function Importacao() {
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const preview = useLeadImportPreview();
  const commit = useLeadImportCommit();
  const batchesQ = useLeadImportBatches({ page: 1, pageSize: 20 });

  // A mutation in flight (preview parse OR commit write) — the dropzone and
  // commit button both gate on this so a user can never swap in a new file
  // (or double-fire commit) while a request is still resolving.
  const busy = preview.isPending || commit.isPending;

  function pickFile(f: File | null) {
    if (busy) return;
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx")) {
      toast.error("Envie um arquivo .xlsx.");
      return;
    }
    setFile(f);
    preview.reset();
    preview.mutate(f, {
      onError: (err) => toast.error(describeError(err, "Erro ao processar a planilha.")),
    });
  }

  function handleCommit() {
    if (!file) return;
    commit.mutate(file, {
      onSuccess: (batch) => {
        toast.success(
          `Importação concluída: ${batch.rows_inserted} novos, ${batch.rows_updated} atualizados.`,
        );
        setFile(null);
        preview.reset();
      },
      onError: (err) => toast.error(describeError(err, "Erro ao confirmar a importação.")),
    });
  }

  const batches = batchesQ.data?.data ?? [];

  return (
    <div className="space-y-6" data-testid="leads-import-success">
      <Card>
        <CardHeader>
          <CardTitle>Importar planilha</CardTitle>
          <CardDescription>
            Arraste um arquivo .xlsx do controle de leads ou clique para escolher. Todas as linhas
            são pré-visualizadas antes de gravar — nada é salvo até você confirmar.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            role="button"
            aria-disabled={busy}
            tabIndex={busy ? -1 : 0}
            onClick={() => !busy && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              if (busy) return;
              pickFile(e.dataTransfer.files?.[0] ?? null);
            }}
            className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
              busy ? "cursor-not-allowed opacity-60" : "cursor-pointer"
            } ${dragActive ? "border-primary bg-primary/5" : "border-border"}`}
            data-testid="leads-import-dropzone"
          >
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">Arraste o arquivo .xlsx aqui ou clique para escolher</p>
            {file && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <FileSpreadsheet className="h-3.5 w-3.5" />
                {file.name}
              </p>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx"
              disabled={busy}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              data-testid="leads-import-file-input"
            />
          </div>

          {preview.isPending && (
            <div
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="leads-import-preview-loading"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Processando planilha...
            </div>
          )}

          {preview.isError && (
            <div className="flex items-center gap-2 text-sm text-destructive" data-testid="leads-import-preview-error">
              <AlertTriangle className="h-4 w-4" />
              {describeError(preview.error, "Erro ao processar a planilha.")}
            </div>
          )}

          {preview.data && (
            <div className="space-y-4" data-testid="leads-import-preview">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatBox label="Linhas lidas" value={preview.data.rows_read} />
                <StatBox label="Novas" value={preview.data.rows_new} />
                <StatBox label="Já existentes" value={preview.data.rows_existing} />
                <StatBox label="Puladas" value={preview.data.rows_skipped} />
              </div>

              {preview.data.warnings.length > 0 && (
                <div className="rounded-md border border-dashed border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                  <p className="mb-1 font-medium">Avisos</p>
                  <ul className="list-inside list-disc space-y-0.5">
                    {preview.data.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {preview.data.unmapped_origens.length > 0 && (
                <UnmappedList
                  title="Origens não mapeadas"
                  hint="Mapeie estes valores em Configuração → Origens antes de confirmar, para não caírem em 'outro'."
                  items={preview.data.unmapped_origens}
                  testId="leads-import-unmapped-origens"
                />
              )}
              {preview.data.unmapped_corretores.length > 0 && (
                <UnmappedList
                  title="Corretores não mapeados"
                  hint="Mapeie estes valores em Configuração → Corretores antes de confirmar."
                  items={preview.data.unmapped_corretores}
                  testId="leads-import-unmapped-corretores"
                />
              )}

              <div className="flex justify-end">
                <Button onClick={handleCommit} disabled={commit.isPending} data-testid="leads-import-commit">
                  {commit.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                  )}
                  Confirmar importação
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Histórico de importações</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {batchesQ.isPending && (
            <div className="p-4" data-testid="leads-batches-loading">
              <TableSkeleton rows={5} columns={6} />
            </div>
          )}
          {batchesQ.isError && (
            <div className="p-4 text-sm text-destructive" data-testid="leads-batches-error">
              Erro ao carregar o histórico.
            </div>
          )}
          {!batchesQ.isPending && !batchesQ.isFetching && !batchesQ.isError && batches.length === 0 && (
            <div className="p-4 text-center text-sm text-muted-foreground" data-testid="leads-batches-empty">
              Nenhuma importação registrada ainda.
            </div>
          )}
          {!batchesQ.isPending && !batchesQ.isError && batches.length > 0 && (
            <div className="overflow-x-auto" data-testid="leads-batches-table">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                    <th className="px-4 py-2">Arquivo</th>
                    <th className="px-4 py-2 text-right">Lidas</th>
                    <th className="px-4 py-2 text-right">Inseridas</th>
                    <th className="px-4 py-2 text-right">Atualizadas</th>
                    <th className="px-4 py-2 text-right">Sinalizadas</th>
                    <th className="px-4 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((b) => (
                    <tr key={b.id} className="border-b last:border-0" data-testid={`leads-batch-row-${b.id}`}>
                      <td className="px-4 py-2">{b.filename}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.rows_read}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.rows_inserted}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.rows_updated}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.rows_flagged}</td>
                      <td className="px-4 py-2">
                        <Badge variant={STATUS_VARIANT[b.status]}>{STATUS_LABEL[b.status]}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3 text-center">
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function UnmappedList({
  title,
  hint,
  items,
  testId,
}: {
  title: string;
  hint: string;
  items: { alias: string; count: number }[];
  testId: string;
}) {
  return (
    <div className="rounded-md border border-dashed border-border p-3" data-testid={testId}>
      <p className="text-sm font-medium">{title}</p>
      <p className="mb-2 text-xs text-muted-foreground">{hint}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <Badge key={item.alias} variant="outline">
            {item.alias} ({item.count})
          </Badge>
        ))}
      </div>
    </div>
  );
}
