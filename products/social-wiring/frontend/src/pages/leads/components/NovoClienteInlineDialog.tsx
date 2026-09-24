/**
 * NovoClienteInlineDialog — the "+" escape hatch next to
 * `ClienteAttachPicker`: register a new cliente's nome + contato without
 * leaving the Leads page or losing the "Novo lead" form underneath.
 *
 * Does NOT call a backend endpoint — see `ClienteAttachPicker`'s module
 * header for why no create-cliente route exists. "Adicionar" hands the
 * typed nome/contato back to the caller as a DRAFT selection; the real
 * `clientes` row is created by `POST /api/leads` (`attach_lead_now`) the
 * moment the outer "Novo lead" form is submitted — exactly how every
 * hand-typed lead's cliente has always come to exist in this product.
 */
import { useState, type FormEvent } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ClienteSelecionado } from "./ClienteAttachPicker";

export interface NovoClienteInlineDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCriado: (cliente: ClienteSelecionado) => void;
  "data-testid"?: string;
}

export function NovoClienteInlineDialog({
  open,
  onOpenChange,
  onCriado,
  "data-testid": testId = "novo-cliente-dialog",
}: NovoClienteInlineDialogProps) {
  const [nome, setNome] = useState("");
  const [contato, setContato] = useState("");
  const nomeValido = nome.trim().length > 0;

  function limpar() {
    setNome("");
    setContato("");
  }

  function fechar() {
    onOpenChange(false);
    limpar();
  }

  function salvar(e: FormEvent) {
    e.preventDefault();
    if (!nomeValido) return;
    onCriado({
      // Client-side-only draft id — never sent to the backend as a real
      // `clientes.id`; `ClienteAttachPicker.contatoParaAnexar` is never
      // called for a draft, only for a row `useClientesBusca` returned.
      id: `novo:${crypto.randomUUID()}`,
      nome: nome.trim(),
      contato: contato.trim() || null,
      isNovo: true,
    });
    limpar();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(next) : fechar())}>
      <DialogContent className="max-w-sm" data-testid={testId}>
        <DialogHeader>
          <DialogTitle>Novo cliente</DialogTitle>
        </DialogHeader>
        <form onSubmit={salvar} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor={`${testId}-nome-input`}>Nome</Label>
            <Input
              id={`${testId}-nome-input`}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Nome completo"
              autoFocus
              data-testid={`${testId}-nome`}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${testId}-contato-input`}>Contato</Label>
            <Input
              id={`${testId}-contato-input`}
              value={contato}
              onChange={(e) => setContato(e.target.value)}
              placeholder="Telefone ou email"
              data-testid={`${testId}-contato`}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={fechar}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!nomeValido} data-testid={`${testId}-salvar`}>
              Adicionar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
