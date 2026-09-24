/**
 * NovoLeadClienteDialog — Base de Leads' "Novo lead" flow (leads-novo-lead),
 * ATTACHED to an already-registered cliente via `ClienteAttachPicker`
 * instead of a blind `cliente_nome` text field.
 *
 * Uses the SAME `POST /api/leads` mutation (`useLeadMutations().create`)
 * every other lead-creation path in this product uses — `FunilVendas`'s own
 * "Novo lead" button (`LeadFormDialog`) included; `BaseDeLeads.tsx` keeps
 * `LeadFormDialog` for EDITING an existing lead's full field set, this
 * dialog only replaces the CREATE path.
 *
 * 🔴 Does NOT create the funil card/atendimento. Migration 034/090's
 * `social_wiring.spawn_funil_card()` trigger does that, server-side, on
 * every `leads` INSERT — this dialog's only job is picking WHO the lead is
 * about and submitting the same request every other creation path already
 * sends. See this slice's delivery note for exactly where that automation
 * lives.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLeadSources } from "@/hooks/useLeadsSources";
import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import { useLeadMutations } from "@/hooks/useLeads";
import type { Lead } from "@/pages/leads/types";
import { ClienteAttachPicker, type ClienteSelecionado } from "./ClienteAttachPicker";
import { describeError } from "../utils";

const NONE = "__none__";

function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}

export interface NovoLeadClienteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NovoLeadClienteDialog({ open, onOpenChange }: NovoLeadClienteDialogProps) {
  const [dataEntrada, setDataEntrada] = useState(hoje);
  const [tipoLead, setTipoLead] = useState<Lead["tipo_lead"]>("novo");
  const [origemId, setOrigemId] = useState<string | null>(null);
  const [corretorId, setCorretorId] = useState<string | null>(null);
  const [cliente, setCliente] = useState<ClienteSelecionado | null>(null);

  const { data: sources } = useLeadSources();
  const { data: corretores } = useLeadCorretores();
  const { create } = useLeadMutations();

  function reset() {
    setDataEntrada(hoje());
    setTipoLead("novo");
    setOrigemId(null);
    setCorretorId(null);
    setCliente(null);
  }

  function fechar() {
    onOpenChange(false);
    reset();
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!cliente) return;
    create.mutate(
      {
        data_entrada: dataEntrada,
        tipo_lead: tipoLead,
        origem_id: origemId,
        corretor_id: corretorId,
        cliente_nome: cliente.nome,
        contato: cliente.contato,
      },
      {
        onSuccess: () => {
          toast.success("Lead criado.");
          // Both modals close on success: this one right here, and
          // `NovoClienteInlineDialog` — which already closed itself the
          // instant its own "Adicionar" ran (`ClienteAttachPicker` sets
          // `novoAberto` back to `false` in the same `onCriado` callback
          // that fills `cliente`), well before this submit ever fires.
          fechar();
        },
        onError: (err) => toast.error(describeError(err, "Erro ao criar lead.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(next) : fechar())}>
      <DialogContent
        className="max-h-[85vh] max-w-lg overflow-y-auto"
        data-testid="novo-lead-cliente-dialog"
      >
        <DialogHeader>
          <DialogTitle>Novo lead</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="novo-lead-cliente-input">Cliente</Label>
            <ClienteAttachPicker
              id="novo-lead-cliente-input"
              value={cliente}
              onChange={setCliente}
              disabled={create.isPending}
              data-testid="novo-lead-cliente-picker"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="novo-lead-data">Data de entrada</Label>
              <Input
                id="novo-lead-data"
                type="date"
                required
                value={dataEntrada}
                onChange={(e) => setDataEntrada(e.target.value)}
                disabled={create.isPending}
                data-testid="novo-lead-data-entrada"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="novo-lead-tipo">Tipo</Label>
              <Select
                value={tipoLead}
                onValueChange={(v) => setTipoLead(v as Lead["tipo_lead"])}
              >
                <SelectTrigger id="novo-lead-tipo" data-testid="novo-lead-tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="novo">Novo</SelectItem>
                  <SelectItem value="retorno">Retorno</SelectItem>
                  <SelectItem value="desconhecido">Desconhecido</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="novo-lead-origem">Origem</Label>
              <Select
                value={origemId ?? NONE}
                onValueChange={(v) => setOrigemId(v === NONE ? null : v)}
              >
                <SelectTrigger id="novo-lead-origem" data-testid="novo-lead-origem">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  {(sources ?? []).map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="novo-lead-corretor">Corretor</Label>
              <Select
                value={corretorId ?? NONE}
                onValueChange={(v) => setCorretorId(v === NONE ? null : v)}
              >
                <SelectTrigger id="novo-lead-corretor" data-testid="novo-lead-corretor">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  {(corretores ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.nome}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={fechar}>
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={!cliente || create.isPending}
              data-testid="novo-lead-submit"
            >
              {create.isPending ? "Salvando..." : "Criar lead"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
