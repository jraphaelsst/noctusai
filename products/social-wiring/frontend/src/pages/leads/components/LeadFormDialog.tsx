/**
 * LeadFormDialog — create/edit form for one `Lead`, "Base de Leads" subtab
 * page-scoped CRUD. Manual day-of-entry is the input mode per §1 of
 * leads-module-PROJECT.md (the future Meta/social wire-up is out of scope).
 */
import { useEffect, useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLeadSources } from "@/hooks/useLeadsSources";
import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import type { Lead, LeadCreateInput } from "@/pages/leads/types";

export interface LeadFormValues extends LeadCreateInput {
  /** Only meaningful when editing (`lead` set) — omitted (`undefined`) on
   * create, so it is never sent on the create payload even if that
   * endpoint also forbids unknown fields. */
  needs_review?: boolean;
}

const NONE = "__none__";

function emptyForm(): LeadFormValues {
  return {
    data_entrada: new Date().toISOString().slice(0, 10),
    codigo_raw: "",
    empreendimento: "",
    regiao: "",
    origem_id: null,
    tipo_lead: "desconhecido",
    cliente_nome: "",
    contato: "",
    corretor_id: null,
    anuncio_tier: null,
    status: "",
    observacoes: "",
    follow_up_data: "",
    follow_up_nota: "",
  };
}

function fromLead(lead: Lead): LeadFormValues {
  return {
    data_entrada: lead.data_entrada,
    codigo_raw: lead.codigo_raw ?? "",
    empreendimento: lead.empreendimento ?? "",
    regiao: lead.regiao ?? "",
    origem_id: lead.origem_id,
    tipo_lead: lead.tipo_lead,
    cliente_nome: lead.cliente_nome ?? "",
    contato: lead.contato ?? "",
    corretor_id: lead.corretor_id,
    anuncio_tier: lead.anuncio_tier,
    status: lead.status ?? "",
    observacoes: lead.observacoes ?? "",
    follow_up_data: lead.follow_up_data ?? "",
    follow_up_nota: lead.follow_up_nota ?? "",
    needs_review: lead.needs_review,
  };
}

function emptyToNull(v: string | null | undefined): string | null {
  return v ? v : null;
}

/**
 * Pydantic rejects `""` for `Optional[date]` (`follow_up_data`) — and more
 * broadly, an empty text input submitted as `""` persists as an empty
 * string, not the NULL that "left it blank" actually means. Coerce every
 * optional text/date field before sending (leads-p0-frontend-ux finding #3
 * — every save 422s when `follow_up_data` is blank, i.e. nearly every one
 * of the 12,177 imported leads).
 */
function cleanFormValues(values: LeadFormValues): LeadFormValues {
  return {
    ...values,
    codigo_raw: emptyToNull(values.codigo_raw),
    empreendimento: emptyToNull(values.empreendimento),
    regiao: emptyToNull(values.regiao),
    cliente_nome: emptyToNull(values.cliente_nome),
    contato: emptyToNull(values.contato),
    status: emptyToNull(values.status),
    observacoes: emptyToNull(values.observacoes),
    follow_up_data: emptyToNull(values.follow_up_data),
    follow_up_nota: emptyToNull(values.follow_up_nota),
  };
}

export interface LeadFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lead?: Lead | null;
  onSubmit: (values: LeadFormValues) => void;
  isPending?: boolean;
}

export function LeadFormDialog({
  open,
  onOpenChange,
  lead,
  onSubmit,
  isPending = false,
}: LeadFormDialogProps) {
  const [form, setForm] = useState<LeadFormValues>(emptyForm());
  const { data: sources } = useLeadSources();
  const { data: corretores } = useLeadCorretores();

  useEffect(() => {
    if (open) {
      setForm(lead ? fromLead(lead) : emptyForm());
    }
  }, [open, lead]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(cleanFormValues(form));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto" data-testid="lead-form-dialog">
        <DialogHeader>
          <DialogTitle>{lead ? "Editar lead" : "Novo lead"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-data">Data de entrada</Label>
              <Input
                id="lead-data"
                type="date"
                required
                value={form.data_entrada}
                onChange={(e) => setForm({ ...form, data_entrada: e.target.value })}
                disabled={isPending}
                data-testid="lead-form-data-entrada"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-tipo">Tipo</Label>
              <Select
                value={form.tipo_lead ?? "desconhecido"}
                onValueChange={(v) => setForm({ ...form, tipo_lead: v as Lead["tipo_lead"] })}
              >
                <SelectTrigger id="lead-tipo" data-testid="lead-form-tipo">
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

          <div className="space-y-1.5">
            <Label htmlFor="lead-cliente">Cliente</Label>
            <Input
              id="lead-cliente"
              value={form.cliente_nome ?? ""}
              onChange={(e) => setForm({ ...form, cliente_nome: e.target.value })}
              disabled={isPending}
              placeholder="Nome da marca"
              data-testid="lead-form-cliente"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-contato">Contato</Label>
              <Input
                id="lead-contato"
                value={form.contato ?? ""}
                onChange={(e) => setForm({ ...form, contato: e.target.value })}
                disabled={isPending}
                placeholder="Telefone ou email"
                data-testid="lead-form-contato"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-tier">Tier do anúncio</Label>
              <Select
                value={form.anuncio_tier ?? NONE}
                onValueChange={(v) =>
                  setForm({ ...form, anuncio_tier: v === NONE ? null : (v as Lead["anuncio_tier"]) })
                }
              >
                <SelectTrigger id="lead-tier" data-testid="lead-form-tier">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  <SelectItem value="simples">Simples</SelectItem>
                  <SelectItem value="destaque">Destaque</SelectItem>
                  <SelectItem value="super_destaque">Super destaque</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-origem">Origem</Label>
              <Select
                value={form.origem_id ?? NONE}
                onValueChange={(v) => setForm({ ...form, origem_id: v === NONE ? null : v })}
              >
                <SelectTrigger id="lead-origem" data-testid="lead-form-origem">
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
              <Label htmlFor="lead-corretor">Corretor</Label>
              <Select
                value={form.corretor_id ?? NONE}
                onValueChange={(v) => setForm({ ...form, corretor_id: v === NONE ? null : v })}
              >
                <SelectTrigger id="lead-corretor" data-testid="lead-form-corretor">
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

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-empreendimento">Empreendimento</Label>
              <Input
                id="lead-empreendimento"
                value={form.empreendimento ?? ""}
                onChange={(e) => setForm({ ...form, empreendimento: e.target.value })}
                disabled={isPending}
                data-testid="lead-form-empreendimento"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-regiao">Região</Label>
              <Input
                id="lead-regiao"
                value={form.regiao ?? ""}
                onChange={(e) => setForm({ ...form, regiao: e.target.value })}
                disabled={isPending}
                data-testid="lead-form-regiao"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="lead-codigo">Código do imóvel</Label>
            <Input
              id="lead-codigo"
              value={form.codigo_raw ?? ""}
              onChange={(e) => setForm({ ...form, codigo_raw: e.target.value })}
              disabled={isPending}
              data-testid="lead-form-codigo"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="lead-observacoes">Observações</Label>
            <Textarea
              id="lead-observacoes"
              value={form.observacoes ?? ""}
              onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
              disabled={isPending}
              data-testid="lead-form-observacoes"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-followup-data">Follow-up (data)</Label>
              <Input
                id="lead-followup-data"
                type="date"
                value={form.follow_up_data ?? ""}
                onChange={(e) => setForm({ ...form, follow_up_data: e.target.value })}
                disabled={isPending}
                data-testid="lead-form-followup-data"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-followup-nota">Follow-up (nota)</Label>
              <Input
                id="lead-followup-nota"
                value={form.follow_up_nota ?? ""}
                onChange={(e) => setForm({ ...form, follow_up_nota: e.target.value })}
                disabled={isPending}
                data-testid="lead-form-followup-nota"
              />
            </div>
          </div>

          {lead && (
            <div className="flex items-center justify-between rounded-md border border-input px-3 py-2">
              <Label htmlFor="lead-resolvido">Resolvido — tirar da revisão</Label>
              <Switch
                id="lead-resolvido"
                checked={!form.needs_review}
                onCheckedChange={(v) => setForm({ ...form, needs_review: !v })}
                disabled={isPending}
                data-testid="lead-form-needs-review-toggle"
              />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending} data-testid="lead-form-submit">
              {isPending ? "Salvando..." : "Salvar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
