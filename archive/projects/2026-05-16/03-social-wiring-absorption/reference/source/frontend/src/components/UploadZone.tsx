/**
 * UploadZone — drag-and-drop file picker tuned for video uploads.
 *
 * Two states: empty (drop hint) and selected (filename + size + clear).
 * Validates extension on drop so the user gets immediate feedback rather
 * than discovering the rejection at upload time.
 */
import { useCallback, useRef, useState } from "react";
import { FileVideo, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const ACCEPTED_VIDEO_EXTENSIONS = [
  ".mp4",
  ".mov",
  ".avi",
  ".mkv",
  ".webm",
  ".m4v",
  ".mpeg",
  ".mpg",
  ".wmv",
] as const;

const ACCEPT_ATTR = ACCEPTED_VIDEO_EXTENSIONS.join(",");

interface UploadZoneProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function hasAcceptedExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_VIDEO_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function UploadZone({ file, onFileChange, disabled }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accept = useCallback(
    (incoming: File | null) => {
      setError(null);
      if (!incoming) {
        onFileChange(null);
        return;
      }
      if (!hasAcceptedExtension(incoming.name)) {
        setError(
          `Formato nao suportado: ${incoming.name}. Aceitos: ${ACCEPTED_VIDEO_EXTENSIONS.join(", ")}.`,
        );
        return;
      }
      onFileChange(incoming);
    },
    [onFileChange],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const dropped = e.dataTransfer.files?.[0] ?? null;
      accept(dropped);
    },
    [accept, disabled],
  );

  if (file) {
    return (
      <div className="rounded-lg border bg-muted/30 p-4">
        <div className="flex items-center gap-3">
          <FileVideo className="h-8 w-8 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{file.name}</div>
            <div className="text-xs text-muted-foreground">
              {formatBytes(file.size)}
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => accept(null)}
            disabled={disabled}
            aria-label="Remover arquivo"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/30 hover:bg-muted/30",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <UploadCloud className="h-10 w-10 text-muted-foreground" />
        <div className="text-sm font-medium">
          Arraste um video aqui ou clique para selecionar
        </div>
        <div className="text-xs text-muted-foreground">
          Formatos: {ACCEPTED_VIDEO_EXTENSIONS.join(", ")}
        </div>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={ACCEPT_ATTR}
          onChange={(e) => accept(e.target.files?.[0] ?? null)}
          disabled={disabled}
        />
      </div>
      {error && <div className="text-xs text-destructive">{error}</div>}
    </div>
  );
}
