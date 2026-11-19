/**
 * UploadFotosField -- the photo picker of a Edição de Fotos batch (file input + the selected list with per-file
 * size flags + the count / size limit messages). Extracted from `NovoLote` so ImobShotAI's funnel reuses it
 * instead of copying it. Presentational: the page owns the `File[]` and the limits (read live off `capacidades`).
 */
import { X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export interface UploadFotosFieldProps {
  arquivos: File[];
  onAdicionar: (files: FileList | null) => void;
  onRemover: (index: number) => void;
  limiteFotos: number;
  limiteBytes: number;
  disabled?: boolean;
}

export function UploadFotosField({
  arquivos,
  onAdicionar,
  onRemover,
  limiteFotos,
  limiteBytes,
  disabled = false,
}: UploadFotosFieldProps) {
  const arquivosExcedeCount = arquivos.length > limiteFotos;
  const arquivoExcedeTamanho = arquivos.find((f) => f.size > limiteBytes) ?? null;

  return (
    <div className="space-y-2">
      <Label htmlFor="arquivos-lote">
        Fotos (até {limiteFotos}, até {formatBytes(limiteBytes)} cada)
      </Label>
      <Input
        id="arquivos-lote"
        type="file"
        accept="image/*"
        multiple
        disabled={disabled}
        onChange={(e) => onAdicionar(e.target.files)}
      />
      {arquivos.length > 0 && (
        <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border p-2 text-sm">
          {arquivos.map((file, i) => (
            <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-2">
              <span className="truncate">
                {file.name}{" "}
                <span
                  className={
                    file.size > limiteBytes ? "text-destructive" : "text-muted-foreground"
                  }
                >
                  ({formatBytes(file.size)})
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemover(i)}
                disabled={disabled}
                aria-label={`Remover ${file.name}`}
                className="shrink-0 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {arquivosExcedeCount && (
        <p role="alert" className="text-xs text-destructive">
          Limite de {limiteFotos} fotos por lote excedido ({arquivos.length} selecionadas).
        </p>
      )}
      {arquivoExcedeTamanho && (
        <p role="alert" className="text-xs text-destructive">
          "{arquivoExcedeTamanho.name}" excede o limite de {formatBytes(limiteBytes)} por foto.
        </p>
      )}
    </div>
  );
}
