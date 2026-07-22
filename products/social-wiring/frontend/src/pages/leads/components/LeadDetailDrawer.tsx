/**
 * LeadDetailDrawer — row-click detail view for one `Lead` ("Base de Leads"
 * subtab, §6 of leads-module-PROJECT.md). Built on the existing `Dialog`
 * primitive (this product has no dedicated Sheet/Drawer component) — a
 * right-weighted modal serving the same "inspect one row without leaving
 * the table" purpose.
 */
import { Pencil, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Lead } from "@/pages/leads/types";

const TIPO_LABEL: Record<Lead["tipo_lead"], string> = {
  novo: "Novo",
  retorno: "Retorno",
  desconhecido: "Desconhecido",
};

const TIER_LABEL: Record<NonNullable<Lead["anuncio_tier"]>, string> = {
  simples: "Simples",
  destaque: "Destaque",
  super_destaque: "Super destaque",
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value ?? <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

export interface LeadDetailDrawerProps {
  lead: Lead | null;
  onOpenChange: (open: boolean) => void;
  onEdit: (lead: Lead) => void;
  onDelete: (lead: Lead) => void;
}

export function LeadDetailDrawer({ lead, onOpenChange, onEdit, onDelete }: LeadDetailDrawerProps) {
  return (
    <Dialog open={!!lead} onOpenChange={(open) => !open && onOpenChange(false)}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto" data-testid="lead-detail-drawer">
        {lead && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {lead.cliente_nome || "Lead sem nome"}
                {lead.needs_review && (
                  <Badge variant="destructive" data-testid="lead-detail-needs-review">
                    Revisar
                  </Badge>
                )}
              </DialogTitle>
            </DialogHeader>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 py-2">
              <Field label="Data de entrada" value={lead.data_entrada} />
              <Field label="Tipo" value={TIPO_LABEL[lead.tipo_lead]} />
              <Field label="Contato" value={lead.contato} />
              <Field
                label="Origem"
                value={
                  lead.origem ? (
                    <span className="inline-flex items-center gap-1.5">
                      {lead.origem.cor && (
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: lead.origem.cor }}
                        />
                      )}
                      {lead.origem.label}
                    </span>
                  ) : (
                    lead.origem_raw
                  )
                }
              />
              <Field label="Corretor" value={lead.corretor?.nome ?? lead.corretor_raw} />
              <Field label="Tier do anúncio" value={lead.anuncio_tier ? TIER_LABEL[lead.anuncio_tier] : null} />
              <Field label="Empreendimento" value={lead.empreendimento} />
              <Field label="Região" value={lead.regiao} />
              <Field label="Código do imóvel" value={lead.codigo_imovel ?? lead.codigo_raw} />
              <Field label="Status" value={lead.status} />
              <Field label="Follow-up" value={lead.follow_up_data} />
              <Field label="Nota de follow-up" value={lead.follow_up_nota} />
              <div className="col-span-2">
                <Field label="Observações" value={lead.observacoes} />
              </div>
              <Field label="Planilha de origem" value={lead.source_sheet} />
              <Field label="Criado em" value={new Date(lead.created_at).toLocaleString("pt-BR")} />
            </dl>

            <DialogFooter className="gap-2 sm:justify-between">
              <Button
                variant="destructive"
                onClick={() => onDelete(lead)}
                data-testid="lead-detail-delete"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Excluir
              </Button>
              <Button onClick={() => onEdit(lead)} data-testid="lead-detail-edit">
                <Pencil className="mr-2 h-4 w-4" />
                Editar
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
