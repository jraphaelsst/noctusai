/** Leads table: Lead · Contato · Operação · Canal · Status, selectable rows, row actions. */
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { GatilhoEnvio, LeadJulia } from "@/hooks/useJuliaLeads";

const OP: Record<string, string> = { compra: "Compra", aluguel: "Aluguel", administracao: "Administração" };
const AUTOMATICOS: GatilhoEnvio[] = ["frio", "captacao", "invalido"];

export function origemEnvio(g: GatilhoEnvio | null | undefined): string {
  if (!g) return "";
  if (g === "manual") return "Enviado manualmente";
  return AUTOMATICOS.includes(g) ? "Enviado automaticamente" : "Enviado pela Julia";
}
export function StatusLead({ lead }: { lead: LeadJulia }) {
  if (lead.status_envio === "enviado")
    return (
      <div>
        <span className="rounded-full bg-success-light px-2 py-0.5 text-xs text-success">Enviado ao SW</span>
        <div className="mt-0.5 text-xs text-muted-foreground">{origemEnvio(lead.gatilho)}</div>
        {lead.lead_id && <Link className="text-xs text-primary underline" to={`/leads?lead=${lead.lead_id}`}>Abrir no SW</Link>}
      </div>
    );
  if (lead.status_envio === "erro")
    return (
      <div>
        <span className="rounded-full bg-danger-light px-2 py-0.5 text-xs text-destructive">Erro no envio</span>
        {lead.erro && <div className="mt-0.5 text-xs text-muted-foreground">{lead.erro}</div>}
      </div>
    );
  return <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Não pronto</span>;
}

export function LeadsTable({
  items, selecionados, onToggle, onToggleTodos, onResumo, onEnviar, enviandoId,
}: {
  items: LeadJulia[];
  selecionados: Set<string>;
  onToggle: (id: string) => void;
  onToggleTodos: (marcar: boolean) => void;
  onResumo: (l: LeadJulia) => void;
  onEnviar: (l: LeadJulia) => void;
  enviandoId: string | null;
}) {
  const todos = items.length > 0 && items.every((l) => selecionados.has(l.id));
  return (
    <table className="w-full text-sm" data-testid="leads-tabela">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="w-8 p-2"><input type="checkbox" aria-label="Selecionar todos" checked={todos} onChange={(e) => onToggleTodos(e.target.checked)} /></th>
          <th className="p-2">Lead</th><th className="p-2">Contato</th><th className="p-2">Operação</th>
          <th className="p-2">Canal</th><th className="p-2">Status</th><th className="p-2" />
        </tr>
      </thead>
      <tbody>
        {items.map((l) => (
          <tr key={l.id} className="border-b align-top" data-testid={`lead-${l.id}`}>
            <td className="p-2"><input type="checkbox" aria-label={`Selecionar ${l.nome ?? l.id}`} checked={selecionados.has(l.id)} onChange={() => onToggle(l.id)} /></td>
            <td className="p-2">
              <div className="font-medium">{l.nome ?? "—"}</div>
              <div className="text-xs text-muted-foreground">{l.atendido_pela_julia ? "Atendido pela Julia" : "Sem atendimento"}</div>
            </td>
            <td className="p-2"><div>{l.telefone ?? "—"}</div><div className="text-xs text-muted-foreground">{l.email}</div></td>
            <td className="p-2"><div>{l.operacao ? OP[l.operacao] : "—"}</div><div className="text-xs text-muted-foreground">{l.codigo_imovel}</div></td>
            <td className="p-2"><div>{l.canal ?? "—"}</div>
              <div className="text-xs text-muted-foreground">{l.primeiro_contato_em ? new Date(l.primeiro_contato_em).toLocaleString("pt-BR") : ""}</div></td>
            <td className="p-2"><StatusLead lead={l} /></td>
            <td className="space-x-1 whitespace-nowrap p-2 text-right">
              <Button asChild variant="ghost" size="sm"><Link to={`/julia/conversas?contato=${l.id}`}>Abrir conversa</Link></Button>
              <Button variant="ghost" size="sm" onClick={() => onResumo(l)}>Ver resumo</Button>
              <Button variant="outline" size="sm" data-testid={`enviar-${l.id}`}
                disabled={l.status_envio === "enviado" || enviandoId === l.id} onClick={() => onEnviar(l)}>
                {enviandoId === l.id ? "Enviando…" : "Enviar ao SW"}
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
