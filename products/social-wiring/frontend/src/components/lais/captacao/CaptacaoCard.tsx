import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { LaisCaptacao } from "@/hooks/useLaisCaptacao";
import { LAIS_PAGES } from "@/nav/lais";

interface Props {
  captacao: LaisCaptacao;
  ocupado: boolean;
  onRegistrar: (c: LaisCaptacao) => void;
  onDescartar: (c: LaisCaptacao) => void;
}

const STATUS_ROTULO: Record<LaisCaptacao["status"], string> = { nova: "Nova", registrada: "Registrada", descartada: "Descartada" };
const SEM = "Não informado";

export function CaptacaoCard({ captacao: c, ocupado, onRegistrar, onDescartar }: Props) {
  const [aberto, setAberto] = useState(false);
  const quando = new Date(c.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  return (
    <li className="rounded-lg border p-3" data-testid="captacao-card">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-wide text-muted-foreground">CAPTAÇÃO</span>
            <span className="rounded bg-muted px-1.5 py-0.5 text-[11px]" data-testid="captacao-status">{STATUS_ROTULO[c.status]}</span>
          </div>
          <p className="text-sm">A Julia identificou uma potencial captação de imóvel</p>
          <p className="text-xs text-muted-foreground">{quando}</p>
        </div>
        <button type="button" aria-label={aberto ? "Recolher" : "Expandir"} aria-expanded={aberto}
          className="rounded p-1 hover:bg-muted" onClick={() => setAberto((v) => !v)}>
          <ChevronDown className={`h-4 w-4 transition-transform ${aberto ? "rotate-180" : ""}`} />
        </button>
      </div>
      {aberto && (
        <div className="mt-2 space-y-3 border-t pt-2 text-sm" data-testid="captacao-detalhe">
          <dl className="space-y-1">
            <div><dt className="inline font-medium">Contato: </dt><dd className="inline">{c.contato.nome || c.contato.telefone || SEM}</dd></div>
            <div><dt className="inline font-medium">Descrição: </dt><dd className="inline">{c.descricao || SEM}</dd></div>
            <div><dt className="inline font-medium">Endereço: </dt><dd className="inline">{c.endereco || SEM}</dd></div>
            <div><dt className="inline font-medium">Operação: </dt><dd className="inline">{c.operacao || SEM}</dd></div>
          </dl>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`${LAIS_PAGES.conversas.href}?contato=${c.contato.id}`} className="text-primary underline">Abrir conversa</Link>
            {c.status === "registrada" && c.imovel_id && (
              <Link to={`/imoveis/${c.imovel_id}`} className="inline-flex items-center gap-1 text-primary underline">
                Ver imóvel <ExternalLink className="h-3 w-3" />
              </Link>
            )}
            {c.status === "nova" && (
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="outline" disabled={ocupado} onClick={() => onDescartar(c)}>Descartar</Button>
                <Button size="sm" disabled={ocupado} onClick={() => onRegistrar(c)}>Registrar captação</Button>
              </div>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
