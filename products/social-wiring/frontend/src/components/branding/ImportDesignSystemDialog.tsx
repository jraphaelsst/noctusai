/**
 * "Importar design system" — pick a design-system FOLDER (tokens.json,
 * README.md, components/, assets/, fonts/), choose the marca that owns it (or
 * import it as the Branding Template), and the server validates + creates or
 * updates the branding. Every rejection reason is listed; nothing is imported
 * partially from an invalid bundle.
 */
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  Field,
  FormError,
  Select,
} from "@noctusai/lib/design-system";

import { useImportDesignSystem, type ImportResult } from "@/hooks/useBranding";
import { useMarcas } from "@/hooks/useMarcas";
import { bundleErrors, readDesignSystemFiles, type ImportFilePayload } from "@/lib/branding";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function ImportDesignSystemDialog({
  open,
  onClose,
  defaultMarcaId,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  defaultMarcaId?: string | null;
  onImported: (result: ImportResult) => void;
}) {
  const marcas = useMarcas();
  const importer = useImportDesignSystem();
  const picker = useRef<HTMLInputElement>(null);
  const [marcaId, setMarcaId] = useState<string>(defaultMarcaId ?? "");
  const [asTemplate, setAsTemplate] = useState(false);
  const [files, setFiles] = useState<ImportFilePayload[]>([]);
  const [folder, setFolder] = useState("");
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);

  const pick = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setError(null);
    setProblems([]);
    setResult(null);
    setReading(true);
    try {
      const read = await readDesignSystemFiles(list);
      setFiles(read);
      const first = (list[0] as File & { webkitRelativePath?: string }).webkitRelativePath;
      setFolder(first ? first.split("/")[0] : `${list.length} arquivo(s)`);
    } catch (err) {
      setFiles([]);
      setError(mensagemErroServidor(err, "Falha ao ler a pasta"));
    } finally {
      setReading(false);
    }
  };

  const canImport = files.length > 0 && (asTemplate || !!marcaId) && !importer.isPending && !reading;

  const submit = async () => {
    setError(null);
    setProblems([]);
    try {
      const r = await importer.mutateAsync({
        marca_id: asTemplate ? null : marcaId,
        is_template: asTemplate,
        files,
      });
      setResult(r);
      toast.success(`Design system ${r.action === "created" ? "importado" : "atualizado"}: ${r.name}`);
      onImported(r);
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao importar o design system"));
      setProblems(bundleErrors(err));
    }
  };

  const close = () => {
    setFiles([]);
    setFolder("");
    setError(null);
    setProblems([]);
    setResult(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={close} title="Importar design system" className="max-w-xl">
      <DialogHeader>
        <h3 className="text-base font-semibold">Importar design system</h3>
        <p className="text-xs text-muted-foreground">
          Escolha a pasta do design system (tokens.json, README.md, components/, assets/, fonts/). Cria o branding ou
          atualiza o existente da mesma marca.
        </p>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <Field label="Pasta do design system" required>
          <input
            ref={picker}
            type="file"
            data-testid="branding-import-folder"
            // @ts-expect-error — non-standard but universally supported folder picker
            webkitdirectory=""
            multiple
            onChange={(e) => void pick(e.target.files)}
            className="block w-full text-xs"
          />
        </Field>
        {reading && <p className="text-xs text-muted-foreground">Lendo arquivos…</p>}
        {folder && !reading && (
          <p className="text-xs" data-testid="branding-import-summary">
            {folder}: {files.length} arquivo(s) lido(s).
          </p>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={asTemplate}
            onChange={(e) => setAsTemplate(e.target.checked)}
            data-testid="branding-import-template"
          />
          Importar como Branding Template (não pertence a uma marca)
        </label>
        {!asTemplate && (
          <Field label="Marca dona do branding" required>
            <Select
              value={marcaId}
              onChange={(e) => setMarcaId(e.target.value)}
              disabled={marcas.isPending && !marcas.data}
              data-testid="branding-import-marca"
            >
              <option value="">Escolha a marca…</option>
              {(marcas.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <FormError message={error} />
        {problems.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-xs text-destructive" data-testid="branding-import-problems">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
        {result && (
          <div className="space-y-1 rounded-md border bg-muted/30 p-3 text-xs" data-testid="branding-import-result">
            <p className="font-medium">
              {result.action === "created" ? "Criado" : "Atualizado"}: {result.name} — {result.components} componente(s),{" "}
              {result.assets} ativo(s), {result.sections} seção(ões).
            </p>
            {result.warnings.map((w) => (
              <p key={w} className="text-amber-700">
                Aviso: {w}
              </p>
            ))}
            {result.ignored.length > 0 && (
              <p className="text-muted-foreground">Não importados: {result.ignored.join(", ")}</p>
            )}
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={close}>
          {result ? "Fechar" : "Cancelar"}
        </Button>
        {!result && (
          <Button variant="primary" disabled={!canImport} onClick={() => void submit()} data-testid="branding-import-submit">
            {importer.isPending ? "Importando…" : "Importar"}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  );
}
