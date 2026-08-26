/**
 * `<ImovelDocumentosCard/>` — the matrícula and the guia de IPTU.
 *
 * 🔴 THE EXTRACTION STATE IS SHOWN, NOT HIDDEN
 * ---------------------------------------------
 * Uploading a matrícula starts a background read that fills the número da
 * matrícula. That read takes seconds to tens of seconds on a scanned
 * certidão, and it can legitimately come back with nothing.
 *
 * If the UI showed only the file, all three outcomes — still reading, read
 * it, found nothing — would look identical: a field that is still empty. The
 * user would conclude the feature does not work, which is the same cost as
 * it actually not working. So each document says where its read got to, and
 * a low-confidence result is offered as a suggestion rather than silently
 * discarded.
 *
 * 🔴 ITS OWN FILE INPUT, HELD BY A REF
 * -------------------------------------
 * Not a shared `getElementById` — that is exactly the bug that would have
 * filed every buyer's upload onto the titular in the card dialog. One input
 * per card instance, reachable only from this instance.
 */
import { useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { ImovelDocumento } from "@/hooks/useImovelDados";
import { TIPOS_DOCUMENTO, formatBytes } from "@/hooks/useImovelDados";

interface Props {
  documentos: ImovelDocumento[];
  loading: boolean;
  uploading: boolean;
  error?: string | null;
  onUpload: (file: File, tipoDocumento: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
}

const TIPO_LABEL: Record<string, string> = Object.fromEntries(
  TIPOS_DOCUMENTO.map((t) => [t.value, t.label]),
);

export default function ImovelDocumentosCard({
  documentos,
  loading,
  uploading,
  error,
  onUpload,
  onRemove,
  onOpen,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [tipo, setTipo] = useState<string>(TIPOS_DOCUMENTO[0].value);

  function pick() {
    inputRef.current?.click();
  }

  function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onUpload(file, tipo);
    // Reset so choosing the SAME file twice still fires a change event.
    e.target.value = "";
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4" />
          Documentos do imóvel
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Select value={tipo} onValueChange={setTipo}>
            <SelectTrigger className="flex-1" aria-label="Tipo de documento">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIPOS_DOCUMENTO.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={pick} disabled={uploading} variant="outline">
            {uploading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Enviar
          </Button>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            onChange={onFileChosen}
            data-testid="imovel-documento-input"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {loading ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : documentos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum documento enviado. Envie a matrícula e o número será lido
            automaticamente.
          </p>
        ) : (
          <ul className="space-y-2">
            {documentos.map((d) => (
              <li
                key={d.id}
                className="flex items-start justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0 space-y-1">
                  <button
                    type="button"
                    onClick={() => onOpen(d.id)}
                    className="truncate text-sm font-medium hover:underline"
                  >
                    {d.nome_original}
                  </button>
                  <p className="text-xs text-muted-foreground">
                    {TIPO_LABEL[d.tipo_documento] ?? d.tipo_documento} ·{" "}
                    {formatBytes(d.tamanho_bytes)}
                  </p>
                  <ExtracaoLinha documento={d} />
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remover ${d.nome_original}`}
                  title="Remover"
                  onClick={() => {
                    const motivo = window.prompt(
                      "Por que este documento está sendo removido?",
                    );
                    // An empty/cancelled prompt is a CANCEL, not a delete with
                    // a blank reason — the backend requires a real motivo.
                    if (motivo && motivo.trim()) onRemove(d.id, motivo.trim());
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** What the automatic read got to — the whole point of showing status. */
function ExtracaoLinha({ documento }: { documento: ImovelDocumento }) {
  const s = documento.extracao_status;
  if (!s) return null;

  if (s === "pendente" || s === "processando") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Lendo o número da matrícula…
      </p>
    );
  }

  if (s === "erro") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-destructive">
        <AlertCircle className="h-3 w-3" />
        Não foi possível ler: {documento.extracao_erro ?? "erro desconhecido"}
      </p>
    );
  }

  if (s === "sem_dados" || !documento.extracao_matricula) {
    return (
      <p className="text-xs text-muted-foreground">
        Documento lido, mas nenhum número de matrícula foi encontrado.
      </p>
    );
  }

  const baixa = documento.extracao_confianca === "baixa";
  // A <div>, not a <p>: `Badge` renders a <div>, and a <div> inside a <p> is
  // invalid nesting that React warns about and browsers silently re-parent.
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CheckCircle2 className="h-3 w-3" />
      Matrícula lida: <strong>{documento.extracao_matricula}</strong>
      {baixa && (
        // Read, but not trusted enough to write on its own. Saying so is what
        // stops a plausible misread becoming an unquestioned fact.
        <Badge variant="outline" className="text-[10px]">
          confirme antes de usar
        </Badge>
      )}
    </div>
  );
}
