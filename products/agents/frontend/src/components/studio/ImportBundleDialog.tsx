/**
 * Import bundle dialog — Agent Studio CONTRACT.md §D5, §F. Shared by
 * `StudioList` (admin "Importar pacote" — the target agent is whatever
 * `bundle.agente.key` says, may create a brand-new studio agent) and the
 * Overview tab (import into THIS agent — a bundle for a different key is
 * refused client-side before any request is sent).
 *
 * Flow: pick a `.json` file → parsed client-side (just enough to show the
 * agent key/nome + rough counts and to enforce the key-mismatch guard) →
 * `dry_run=true` shows the server's plan + `avisos` → "Importar"
 * (`dry_run=false`) applies it. Never publishes (§D5) — the dialog says so.
 */
import { useRef, useState } from "react";
import { AlertTriangle, FileJson, Upload } from "lucide-react";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, FormError } from "@noctusai/lib/design-system";
import { useImportBundle, type ImportBundlePreview, type ImportBundleSummary } from "@/hooks/studio/useImportBundle";
import { errorMessage } from "@/lib/errors";

const EXPECTED_FORMATO = "noctus.agent-bundle/v1";

function countDocs(bundle: ImportBundlePreview): number {
  return (bundle.conhecimento ?? []).reduce((acc, c) => acc + (c.documentos?.length ?? 0), 0);
}

/** Minimal client-side shape check — the backend is the strict-schema
 * authority (§F); this only needs enough to show a preview and find the
 * target key BEFORE sending anything. */
function parseBundle(raw: string): { bundle: ImportBundlePreview } | { error: string } {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { error: "O arquivo não é um JSON válido." };
  }
  if (typeof json !== "object" || json === null) return { error: "O arquivo não é um objeto JSON." };
  const obj = json as Record<string, unknown>;
  if (obj.formato !== EXPECTED_FORMATO) {
    return { error: `Formato inesperado (esperado "${EXPECTED_FORMATO}").` };
  }
  const agente = obj.agente as Record<string, unknown> | undefined;
  if (!agente || typeof agente.key !== "string" || typeof agente.nome !== "string") {
    return { error: 'Pacote sem "agente.key"/"agente.nome".' };
  }
  return { bundle: obj as unknown as ImportBundlePreview };
}

export interface ImportBundleDialogProps {
  /** Set on the Overview tab (import into THIS agent) — a bundle whose
   * `agente.key` differs is refused before any request. Omitted on
   * `/studio` (StudioList), where the target key comes from the bundle. */
  expectedAgentKey?: string;
  onClose: () => void;
  /** Called once a non-dry-run import succeeds, with the imported agent's key. */
  onImported: (key: string) => void;
}

export function ImportBundleDialog({ expectedAgentKey, onClose, onImported }: ImportBundleDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [bundle, setBundle] = useState<ImportBundlePreview | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [plan, setPlan] = useState<ImportBundleSummary | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const importMutation = useImportBundle();

  const keyMismatch = !!expectedAgentKey && !!bundle && bundle.agente.key !== expectedAgentKey;

  function reset() {
    setBundle(null);
    setPlan(null);
    setParseError(null);
    setServerError(null);
  }

  function handleFile(file: File) {
    reset();
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      const result = parseBundle(text);
      if ("error" in result) setParseError(result.error);
      else setBundle(result.bundle);
    };
    reader.onerror = () => setParseError("Não foi possível ler o arquivo.");
    reader.readAsText(file);
  }

  async function handleDryRun() {
    if (!bundle || keyMismatch) return;
    setServerError(null);
    try {
      const summary = await importMutation.mutateAsync({ key: bundle.agente.key, bundle, dryRun: true });
      setPlan(summary);
    } catch (err) {
      setServerError(errorMessage(err));
    }
  }

  async function handleImport() {
    if (!bundle || keyMismatch) return;
    setServerError(null);
    try {
      await importMutation.mutateAsync({ key: bundle.agente.key, bundle, dryRun: false });
      onImported(bundle.agente.key);
    } catch (err) {
      setServerError(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Importar pacote de agente" className="max-w-xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">Importar pacote de agente</h2>
      </DialogHeader>
      <DialogBody className="space-y-4" data-testid="import-bundle-dialog">
        <p className="text-xs text-muted-foreground">
          Substitui as seções e skills do rascunho do agente; conhecimento, avaliações e clientes são atualizados por
          slug (criados ou atualizados, nada é removido). Nunca publica automaticamente — o rascunho fica pronto para
          revisão na aba Versões.
        </p>

        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <FileJson className="mr-1.5 h-3.5 w-3.5" />
            {fileName ? "Trocar arquivo" : "Escolher arquivo .json"}
          </Button>
          {fileName && <span className="text-xs text-muted-foreground">{fileName}</span>}
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            data-testid="import-bundle-file-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
              e.target.value = "";
            }}
          />
        </div>

        {parseError && <FormError message={parseError} />}

        {bundle && !parseError && (
          <div className="rounded-md border border-border p-3 text-sm" data-testid="import-bundle-preview">
            <p className="font-medium text-foreground">
              {bundle.agente.nome} <span className="font-mono text-xs text-muted-foreground">({bundle.agente.key})</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {(bundle.secoes ?? []).length} seções · {(bundle.skills ?? []).length} skills ·{" "}
              {(bundle.conhecimento ?? []).length} coleções ({countDocs(bundle)} documentos) ·{" "}
              {(bundle.evals ?? []).length} casos de avaliação · {(bundle.clientes ?? []).length} clientes
            </p>
          </div>
        )}

        {keyMismatch && bundle && (
          <div
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive"
            role="alert"
            data-testid="import-bundle-key-mismatch"
          >
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <span>
              Este pacote é do agente <strong>{bundle.agente.key}</strong>, mas você está importando para{" "}
              <strong>{expectedAgentKey}</strong>. Abra o Agent Studio deste agente pela lista (<code>/studio</code>) ou
              escolha o pacote correto.
            </span>
          </div>
        )}

        {serverError && <FormError message={serverError} />}

        {plan && (
          <div className="space-y-1.5 rounded-md border border-border bg-muted/30 p-3 text-xs" data-testid="import-bundle-plan">
            <p className="font-medium text-foreground">
              Plano {plan.dry_run ? "(simulação — nada foi salvo)" : "(aplicado)"}
              {plan.agente.criado && <Badge variant="outline" className="ml-2">novo agente</Badge>}
            </p>
            <p>
              Rascunho: {plan.rascunho.secoes} seções · {plan.rascunho.skills} skills · {plan.rascunho.arquivos} arquivos
            </p>
            <p>
              Conhecimento: {plan.conhecimento.colecoes_criadas} coleções criadas · {plan.conhecimento.documentos_criados}{" "}
              documentos criados · {plan.conhecimento.documentos_atualizados} atualizados ·{" "}
              {plan.conhecimento.documentos_inalterados} inalterados
            </p>
            <p>
              Avaliações: {plan.evals.criados} criados · {plan.evals.atualizados} atualizados
            </p>
            <p>Clientes: {plan.clientes.criados} criados</p>
            {plan.avisos.length > 0 && (
              <ul className="ml-4 list-disc text-amber-700">
                {plan.avisos.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        {!plan || plan.dry_run ? (
          <Button
            variant="outline"
            onClick={handleDryRun}
            disabled={!bundle || keyMismatch || importMutation.isPending}
            data-testid="import-bundle-dry-run"
          >
            {importMutation.isPending && !plan ? "Simulando…" : "Ver plano"}
          </Button>
        ) : null}
        {plan && plan.dry_run && (
          <Button
            variant="primary"
            onClick={handleImport}
            disabled={keyMismatch || importMutation.isPending}
            data-testid="import-bundle-confirm"
          >
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            {importMutation.isPending ? "Importando…" : "Importar"}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  );
}
