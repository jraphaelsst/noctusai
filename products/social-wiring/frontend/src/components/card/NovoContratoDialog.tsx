/**
 * NovoContratoDialog — upload the first version of a new contract.
 *
 * A SIBLING of the card, same reason `CriarRoteiroDialog` and
 * `AdicionarCompradorDialog` are: a Dialog nested inside `ClienteCardDialog`'s
 * own Dialog content fights the outer focus trap and scroll lock. So this is
 * rendered top-level by `ClienteDetailModal`, with `ContratosPanel`'s "Novo
 * contrato" button only flipping the `open` prop it is handed.
 *
 * Client-side file validation (MIME/extension + 25 MB) mirrors the server's
 * own 422 gate — the user finds out from the form, not from a round trip.
 *
 * Presentational: `onCriar` is the only callback out; the caller owns the
 * multipart POST and the toast.
 */
import { useState } from "react";
import type { ChangeEvent } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  CONTRATO_ACCEPT_ATTR,
  CONTRATO_MODELO_OPTIONS,
  MODELO_LABEL,
  formatBytes,
  validateContratoFile,
  type ContratoModelo,
} from "@/hooks/useContratos";

export interface NovoContratoInput {
  file: File;
  titulo: string;
  modelo: ContratoModelo;
  rotulo?: string;
}

export interface NovoContratoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCriar: (input: NovoContratoInput) => void;
  saving?: boolean;
}

const TITULO_MAX = 200;

export function NovoContratoDialog({
  open,
  onOpenChange,
  onCriar,
  saving,
}: NovoContratoDialogProps) {
  const [titulo, setTitulo] = useState("");
  const [modelo, setModelo] = useState<ContratoModelo>("compra_venda");
  const [rotulo, setRotulo] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  function escolherArquivo(e: ChangeEvent<HTMLInputElement>) {
    const escolhido = e.target.files?.[0] ?? null;
    if (!escolhido) {
      setFile(null);
      setFileError(null);
      return;
    }
    const erro = validateContratoFile(escolhido);
    if (erro) {
      setFile(null);
      setFileError(erro);
    } else {
      setFile(escolhido);
      setFileError(null);
    }
  }

  function fechar(aberto: boolean) {
    if (!aberto) {
      setTitulo("");
      setModelo("compra_venda");
      setRotulo("");
      setFile(null);
      setFileError(null);
    }
    onOpenChange(aberto);
  }

  const tituloValido = titulo.trim().length > 0 && titulo.trim().length <= TITULO_MAX;
  const podeSalvar = tituloValido && !!file && !fileError && !saving;

  function salvar() {
    if (!podeSalvar || !file) return;
    onCriar({
      file,
      titulo: titulo.trim(),
      modelo,
      rotulo: rotulo.trim() || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={fechar}>
      <DialogContent data-testid="novo-contrato-dialog">
        <DialogHeader>
          <DialogTitle>Novo contrato</DialogTitle>
          <DialogDescription>
            Envie o arquivo do contrato — PDF, DOCX ou DOC, até 25 MB.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="contrato-titulo">Título</Label>
            <Input
              id="contrato-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Contrato de compra e venda"
              maxLength={TITULO_MAX}
              data-testid="contrato-titulo"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="contrato-modelo">Modelo</Label>
            <Select value={modelo} onValueChange={(v) => setModelo(v as ContratoModelo)}>
              <SelectTrigger id="contrato-modelo" data-testid="contrato-modelo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONTRATO_MODELO_OPTIONS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {MODELO_LABEL[m]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="contrato-rotulo">Rótulo da versão (opcional)</Label>
            <Input
              id="contrato-rotulo"
              value={rotulo}
              onChange={(e) => setRotulo(e.target.value)}
              placeholder="ex.: REV 1"
              data-testid="contrato-rotulo"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="contrato-arquivo">Arquivo</Label>
            <Input
              id="contrato-arquivo"
              type="file"
              accept={CONTRATO_ACCEPT_ATTR}
              onChange={escolherArquivo}
              data-testid="contrato-arquivo"
            />
            {fileError && (
              <p className="text-xs text-destructive" data-testid="contrato-arquivo-erro">
                {fileError}
              </p>
            )}
            {file && !fileError && (
              <p className="text-xs text-muted-foreground">
                {file.name} · {formatBytes(file.size)}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => fechar(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={salvar} disabled={!podeSalvar} data-testid="contrato-salvar">
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Criar contrato
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
