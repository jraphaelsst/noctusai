/** "Importar arquivo para o cérebro" — dropzone + client validation (contract §6). */
import { useEffect, useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useEnviarArquivo } from "@/hooks/useCerebro";
import { mensagemErro, validarArquivo } from "./labels";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  brainId: string;
}

export function ImportarArquivoModal({ open, onOpenChange, brainId }: Props) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const enviar = useEnviarArquivo();

  useEffect(() => {
    if (open) {
      setArquivo(null);
      setErro(null);
    }
  }, [open]);

  function escolher(f: File | null) {
    setArquivo(f);
    setErro(f ? validarArquivo(f) : null);
  }

  async function onEnviar() {
    const msg = validarArquivo(arquivo);
    if (msg) {
      setErro(msg);
      return;
    }
    try {
      await enviar.mutateAsync({ id: brainId, file: arquivo as File });
      toast.success("Arquivo enviado. O conteúdo será anexado ao cérebro em instantes.");
      onOpenChange(false);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível enviar o arquivo."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Importar arquivo para o cérebro</DialogTitle>
          <DialogDescription>O conteúdo será adicionado abaixo do texto já existente no cérebro.</DialogDescription>
        </DialogHeader>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            escolher(e.dataTransfer.files?.[0] ?? null);
          }}
          className="flex w-full flex-col items-center gap-2 rounded-md border-2 border-dashed p-8 text-sm text-muted-foreground hover:bg-muted/40"
        >
          <Upload className="h-6 w-6" />
          {arquivo ? <strong className="text-foreground">{arquivo.name}</strong> : "Clique para escolher ou arraste o arquivo aqui"}
          <span className="text-xs">PDF DOCX TXT MD CSV · máx. 20 MB</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          data-testid="importar-arquivo-input"
          className="hidden"
          accept=".pdf,.docx,.txt,.md,.csv"
          onChange={(e) => escolher(e.target.files?.[0] ?? null)}
        />
        {erro && (
          <p role="alert" className="text-sm text-destructive">
            {erro}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={enviar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => void onEnviar()} disabled={enviar.isPending}>
            {enviar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            Enviar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
