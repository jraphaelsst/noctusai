/**
 * Multi-file skill reference-file upload — CONTRACT.md §G item 2 (same
 * treatment as `KnowledgeUploadDialog`, one skill's `arquivos` instead of a
 * knowledge collection's documents). `caminho` is front-matter `caminho`, else
 * `references/<filename>` (`caminhoFromFile`, `@/lib/markdownUpload.ts`); título comes
 * from front matter or the first `# heading`. Chunked upload
 * (`SKILL_FILES_BATCH_MAX` items / `SKILL_FILES_BATCH_MAX_BYTES` per call)
 * with a progress indicator and a final per-file result summary — a failed
 * chunk (network/5xx, or the whole-call 409 `version_immutable` when the
 * version stopped being a rascunho mid-upload) never abandons the rest.
 */
import { useRef, useState } from "react";
import { FileUp, Trash2, UploadCloud } from "lucide-react";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, FormError, Progress } from "@noctusai/lib/design-system";
import { SKILL_FILES_BATCH_MAX, SKILL_FILES_BATCH_MAX_BYTES } from "@/api/studio/batchPaths";
import type { SkillFileBatchItem, SkillFilesBatchResponse } from "@/api/studio/types";
import { useBatchUpsertSkillFiles } from "@/hooks/studio/useVersions";
import { errorMessage } from "@/lib/errors";
import { chunkBySizeAndCount, chunkFailed, sendInChunks, type ChunkResult } from "@/lib/batchUpload";
import { caminhoFromFile, firstMarkdownHeading, formatFileSize, parseFrontMatter, readFileAsText, titleFromFilename } from "@/lib/markdownUpload";
import { BatchUploadResultList, type BatchUploadResultEntry } from "./BatchUploadResultList";

const ACCEPTED_EXTENSIONS = [".md", ".markdown", ".txt"];
const BATCH_LIMITS = { maxCount: SKILL_FILES_BATCH_MAX, maxBytes: SKILL_FILES_BATCH_MAX_BYTES };

interface PreviewFile {
  uid: string;
  fileName: string;
  size: number;
  arquivo: SkillFileBatchItem;
}

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

async function parseSkillFile(file: File): Promise<PreviewFile> {
  const raw = await readFileAsText(file);
  const { data, content } = parseFrontMatter(raw);
  const caminho = caminhoFromFile(file, data.caminho);
  const titulo = data.titulo?.trim() || firstMarkdownHeading(content) || titleFromFilename(file.name);
  return {
    uid: `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`,
    fileName: file.name,
    size: file.size,
    arquivo: { caminho, titulo, conteudo: content.trim() },
  };
}

function buildResults(chunkResults: ChunkResult<SkillFilesBatchResponse>[]): BatchUploadResultEntry[] {
  const out: BatchUploadResultEntry[] = [];
  for (const cr of chunkResults) {
    if (chunkFailed(cr)) {
      const reason = errorMessage(cr.error);
      for (const item of cr.items as SkillFileBatchItem[]) {
        out.push({ key: item.caminho, label: item.caminho, status: "erro", erro: reason });
      }
    } else {
      for (const r of cr.response.resultados) {
        out.push({ key: r.caminho, label: r.caminho, status: r.status, erro: r.erro });
      }
    }
  }
  return out;
}

export interface SkillFilesUploadDialogProps {
  agentKey: string;
  draftId: string | null;
  skillId: string;
  onClose: () => void;
}

export function SkillFilesUploadDialog({ agentKey, draftId, skillId, onClose }: SkillFilesUploadDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<PreviewFile[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ sent: number; total: number } | null>(null);
  const [results, setResults] = useState<BatchUploadResultEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const batchUpsert = useBatchUpsertSkillFiles(agentKey, draftId);

  async function handleFiles(fileList: FileList | File[]) {
    const list = Array.from(fileList);
    const accepted = list.filter(isAcceptedFile);
    const rejected = list.length - accepted.length;
    const parsed = await Promise.all(
      accepted.map(async (file) => {
        try {
          return await parseSkillFile(file);
        } catch (err) {
          return { error: `${file.name}: ${errorMessage(err)}` };
        }
      }),
    );
    const ok = parsed.filter((p): p is PreviewFile => !("error" in p));
    const errs = parsed.filter((p): p is { error: string } => "error" in p).map((p) => p.error);
    if (rejected > 0) errs.unshift(`${rejected} arquivo${rejected === 1 ? "" : "s"} ignorado${rejected === 1 ? "" : "s"} (extensão não suportada).`);
    setFiles((prev) => [...prev, ...ok]);
    setParseErrors(errs);
  }

  function removeFile(uid: string) {
    setFiles((prev) => prev.filter((f) => f.uid !== uid));
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setError(null);
    setResults(null);
    setProgress({ sent: 0, total: files.length });
    try {
      const chunkResults = await sendInChunks(
        files.map((f) => f.arquivo),
        BATCH_LIMITS,
        (batch) => batchUpsert.mutateAsync({ skillId, arquivos: batch }),
        (sent, total) => setProgress({ sent, total }),
      );
      setResults(buildResults(chunkResults));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProgress(null);
    }
  }

  const sending = progress !== null;
  const chunkCount = chunkBySizeAndCount(
    files.map((f) => f.arquivo),
    BATCH_LIMITS,
  ).length;

  return (
    <Dialog open onClose={onClose} title="Enviar arquivos de referência" className="max-w-2xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">Enviar arquivos de referência</h2>
      </DialogHeader>
      <DialogBody className="space-y-4" data-testid="skill-files-upload-dialog">
        <p className="text-xs text-muted-foreground">
          Arraste arquivos <code>.md</code>/<code>.markdown</code>/<code>.txt</code> ou escolha-os abaixo. O caminho
          é <code>references/&lt;nome-do-arquivo&gt;</code> (como a skill cita o arquivo), a menos que o front matter
          traga <code>caminho:</code>. O título vem do front matter ou do primeiro <code># título</code>.
        </p>

        <div
          className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center text-sm text-muted-foreground ${
            dragOver ? "border-primary bg-primary/5" : "border-border"
          }`}
          data-testid="skill-files-upload-dropzone"
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files.length > 0) void handleFiles(e.dataTransfer.files);
          }}
        >
          <UploadCloud className="h-6 w-6" />
          <p>Arraste arquivos aqui</p>
          <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <FileUp className="mr-1.5 h-3.5 w-3.5" />
            Escolher arquivos
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.markdown,.txt,text/markdown,text/plain"
            className="hidden"
            data-testid="skill-files-upload-file-input"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) void handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {parseErrors.length > 0 && (
          <ul className="list-disc pl-4 text-xs text-destructive">
            {parseErrors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}

        {files.length > 0 && (
          <div className="space-y-1.5" data-testid="skill-files-upload-preview">
            <p className="text-xs font-medium text-foreground">
              {files.length} arquivo{files.length === 1 ? "" : "s"} pronto{files.length === 1 ? "" : "s"} para envio
              {chunkCount > 1 && ` · enviado em ${chunkCount} lotes de até ${SKILL_FILES_BATCH_MAX}`}
            </p>
            <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-md border border-border text-xs">
              {files.map((f) => (
                <li key={f.uid} className="flex items-center gap-2 px-2 py-1.5" data-testid={`skill-files-upload-row-${f.arquivo.caminho}`}>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-foreground">{f.arquivo.titulo}</p>
                    <p className="truncate font-mono text-muted-foreground">
                      {f.arquivo.caminho} · {formatFileSize(f.size)}
                    </p>
                  </div>
                  <Button size="icon" variant="ghost" aria-label={`Remover ${f.fileName}`} onClick={() => removeFile(f.uid)} disabled={sending}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {progress && (
          <div className="space-y-1" data-testid="skill-files-upload-progress">
            <Progress value={(progress.sent / Math.max(1, progress.total)) * 100} />
            <p className="text-xs text-muted-foreground">
              enviando {progress.sent}/{progress.total}…
            </p>
          </div>
        )}

        {error && <FormError message={error} />}

        {results && <BatchUploadResultList results={results} />}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={onClose}>
          {results ? "Fechar" : "Cancelar"}
        </Button>
        {!results && (
          <Button
            variant="primary"
            onClick={handleUpload}
            disabled={files.length === 0 || sending || batchUpsert.isPending}
            data-testid="skill-files-upload-submit"
          >
            {sending ? "Enviando…" : `Enviar ${files.length || ""} arquivo${files.length === 1 ? "" : "s"}`}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  );
}
