/**
 * Multi-file knowledge document upload — CONTRACT.md §G item 1 ("BLOCKING
 * — knowledge documents can only be typed one at a time"). Drop zone / file
 * picker (`.md`/`.markdown`/`.txt`, multiple) → each file parsed
 * client-side into one document (front matter when present, filename/first
 * heading fallback otherwise) → a removable preview list → chunked upload
 * (`KNOWLEDGE_DOCUMENTS_BATCH_MAX` items / `KNOWLEDGE_DOCUMENTS_BATCH_MAX_BYTES`
 * per call, `sendInChunks`) with a visible "enviando N/total…" indicator →
 * a final per-file result summary. A failed chunk (network/5xx/409) is
 * recorded as an `erro` result for every document in it and the loop still
 * sends the remaining chunks — never abandons the rest of the upload. A
 * per-item `"erro"` from the backend itself (e.g. `slug_in_other_collection`)
 * surfaces the same way, unchanged.
 */
import { useRef, useState } from "react";
import { FileUp, Trash2, UploadCloud } from "lucide-react";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, FormError, Progress } from "@noctusai/lib/design-system";
import { KNOWLEDGE_DOCUMENTS_BATCH_MAX, KNOWLEDGE_DOCUMENTS_BATCH_MAX_BYTES } from "@/api/studio/batchPaths";
import type { DocumentTipo, KnowledgeDocumentBatchItem, KnowledgeDocumentsBatchResponse, Provenance } from "@/api/studio/types-ke";
import { DOCUMENT_TIPOS } from "@/api/studio/types-ke";
import { useBatchCreateDocuments } from "@/hooks/studio/useKnowledge";
import { errorMessage } from "@/lib/errors";
import { chunkBySizeAndCount, chunkFailed, sendInChunks, type ChunkResult } from "@/lib/batchUpload";
import { firstMarkdownHeading, formatFileSize, parseFrontMatter, readFileAsText, slugFromFilename, titleFromFilename } from "@/lib/markdownUpload";
import { BatchUploadResultList, type BatchUploadResultEntry } from "./BatchUploadResultList";

const ACCEPTED_EXTENSIONS = [".md", ".markdown", ".txt"];
const DEFAULT_TIPO: DocumentTipo = "fonte";
const BATCH_LIMITS = { maxCount: KNOWLEDGE_DOCUMENTS_BATCH_MAX, maxBytes: KNOWLEDGE_DOCUMENTS_BATCH_MAX_BYTES };

interface PreviewDoc {
  uid: string;
  fileName: string;
  size: number;
  doc: KnowledgeDocumentBatchItem;
}

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isKnownTipo(value: string | undefined): value is DocumentTipo {
  return !!value && (DOCUMENT_TIPOS as readonly string[]).includes(value);
}

const PROVENANCE_KEYS: readonly (keyof Provenance)[] = ["autor", "origem", "referencia", "pagina", "licenca", "notas"];

/**
 * Backend `proveniencia` is the structured `Provenance` object. Two front-matter
 * shapes reach it: a scalar line (`proveniencia: "Curso — aula 1"`, mapped onto
 * `origem`, the field closest to "where this came from") or a nested block of
 * `Provenance` fields. An unknown nested key THROWS — the server rejects it
 * (strict model) and dropping it here would lose provenance silently; the
 * caller reports it as that file's parse error.
 */
function provenanceFromFrontMatter(scalar: string | undefined, block: Record<string, string> | undefined): Provenance | undefined {
  if (block) {
    const unknown = Object.keys(block).filter((k) => !(PROVENANCE_KEYS as readonly string[]).includes(k));
    if (unknown.length > 0) {
      throw new Error(`proveniencia com campo(s) desconhecido(s): ${unknown.join(", ")} (aceitos: ${PROVENANCE_KEYS.join(", ")})`);
    }
    return Object.keys(block).length > 0 ? (block as Provenance) : undefined;
  }
  return scalar?.trim() ? { origem: scalar.trim() } : undefined;
}

async function parseKnowledgeFile(file: File): Promise<PreviewDoc> {
  const raw = await readFileAsText(file);
  const { data, nested, content } = parseFrontMatter(raw);
  const slug = data.slug?.trim() || slugFromFilename(file.name);
  const titulo = data.titulo?.trim() || firstMarkdownHeading(content) || titleFromFilename(file.name);
  const tipo = isKnownTipo(data.tipo) ? data.tipo : DEFAULT_TIPO;
  const resumo = data.resumo?.trim() || undefined;
  const proveniencia = provenanceFromFrontMatter(data.proveniencia, nested.proveniencia);
  return {
    uid: `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`,
    fileName: file.name,
    size: file.size,
    doc: { slug, titulo, tipo, conteudo: content.trim(), resumo, proveniencia },
  };
}

function buildResults(
  chunkResults: ChunkResult<KnowledgeDocumentsBatchResponse>[],
): BatchUploadResultEntry[] {
  const out: BatchUploadResultEntry[] = [];
  for (const cr of chunkResults) {
    if (chunkFailed(cr)) {
      const reason = errorMessage(cr.error);
      for (const item of cr.items as KnowledgeDocumentBatchItem[]) {
        out.push({ key: item.slug, label: item.slug, status: "erro", erro: reason });
      }
    } else {
      for (const r of cr.response.resultados) {
        out.push({ key: r.slug, label: r.slug, status: r.status, erro: r.erro });
      }
    }
  }
  return out;
}

export interface KnowledgeUploadDialogProps {
  agentKey: string;
  collectionId: string;
  onClose: () => void;
}

export function KnowledgeUploadDialog({ agentKey, collectionId, onClose }: KnowledgeUploadDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [docs, setDocs] = useState<PreviewDoc[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ sent: number; total: number } | null>(null);
  const [results, setResults] = useState<BatchUploadResultEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const batchCreate = useBatchCreateDocuments(agentKey, collectionId);

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    const accepted = files.filter(isAcceptedFile);
    const rejected = files.length - accepted.length;
    const parsed = await Promise.all(
      accepted.map(async (file) => {
        try {
          return await parseKnowledgeFile(file);
        } catch (err) {
          return { error: `${file.name}: ${errorMessage(err)}` };
        }
      }),
    );
    const ok = parsed.filter((p): p is PreviewDoc => !("error" in p));
    const errs = parsed.filter((p): p is { error: string } => "error" in p).map((p) => p.error);
    if (rejected > 0) errs.unshift(`${rejected} arquivo${rejected === 1 ? "" : "s"} ignorado${rejected === 1 ? "" : "s"} (extensão não suportada).`);
    setDocs((prev) => [...prev, ...ok]);
    setParseErrors(errs);
  }

  function removeDoc(uid: string) {
    setDocs((prev) => prev.filter((d) => d.uid !== uid));
  }

  async function handleUpload() {
    if (docs.length === 0) return;
    setError(null);
    setResults(null);
    setProgress({ sent: 0, total: docs.length });
    try {
      const chunkResults = await sendInChunks(
        docs.map((d) => d.doc),
        BATCH_LIMITS,
        (batch) => batchCreate.mutateAsync(batch),
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
    docs.map((d) => d.doc),
    BATCH_LIMITS,
  ).length;

  return (
    <Dialog open onClose={onClose} title="Enviar documentos" className="max-w-2xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">Enviar documentos</h2>
      </DialogHeader>
      <DialogBody className="space-y-4" data-testid="knowledge-upload-dialog">
        <p className="text-xs text-muted-foreground">
          Arraste arquivos <code>.md</code>/<code>.markdown</code>/<code>.txt</code> ou escolha-os abaixo. Front matter
          (<code>slug</code>/<code>titulo</code>/<code>tipo</code>/<code>proveniencia</code>) é lido quando presente;
          sem front matter, o slug vem do nome do arquivo e o título do primeiro <code># título</code> (ou do nome do
          arquivo).
        </p>

        <div
          className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center text-sm text-muted-foreground ${
            dragOver ? "border-primary bg-primary/5" : "border-border"
          }`}
          data-testid="knowledge-upload-dropzone"
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
            data-testid="knowledge-upload-file-input"
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

        {docs.length > 0 && (
          <div className="space-y-1.5" data-testid="knowledge-upload-preview">
            <p className="text-xs font-medium text-foreground">
              {docs.length} documento{docs.length === 1 ? "" : "s"} pronto{docs.length === 1 ? "" : "s"} para envio
              {chunkCount > 1 && ` · enviado em ${chunkCount} lotes de até ${KNOWLEDGE_DOCUMENTS_BATCH_MAX}`}
            </p>
            <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-md border border-border text-xs">
              {docs.map((d) => (
                <li key={d.uid} className="flex items-center gap-2 px-2 py-1.5" data-testid={`knowledge-upload-row-${d.doc.slug}`}>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-foreground">{d.doc.titulo}</p>
                    <p className="truncate text-muted-foreground">
                      <span className="font-mono">{d.doc.slug}</span> · <Badge variant="outline">{d.doc.tipo}</Badge> ·{" "}
                      {formatFileSize(d.size)}
                    </p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Remover ${d.fileName}`}
                    onClick={() => removeDoc(d.uid)}
                    disabled={sending}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {progress && (
          <div className="space-y-1" data-testid="knowledge-upload-progress">
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
            disabled={docs.length === 0 || sending || batchCreate.isPending}
            data-testid="knowledge-upload-submit"
          >
            {sending ? "Enviando…" : `Enviar ${docs.length || ""} documento${docs.length === 1 ? "" : "s"}`}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  );
}
