import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { HandoffDetalhe } from "@/components/julia/notificacoes/HandoffDetalhe";
import { desescaparEntidades, mascararIdentidade } from "@/lib/mascaraIdentidade";
import { metaTipo, type JuliaNotificacao } from "@/hooks/useJuliaNotificacoes";

interface Props { notificacao: JuliaNotificacao; onLer: (id: string) => void }

export function NotificacaoCard({ notificacao: n, onLer }: Props) {
  const [aberto, setAberto] = useState(false);
  const { categoria } = metaTipo(n.tipo);
  const texto = n.titulo || n.mensagem || "";
  const quando = new Date(n.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  return (
    <li className={`rounded-lg border p-3 ${n.is_read ? "bg-background" : "bg-primary/5"}`} data-testid="notificacao-card">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-wide text-muted-foreground">{categoria}</span>
            {!n.is_read && <span className="h-2 w-2 rounded-full bg-primary" aria-label="Não lida" />}
          </div>
          <p className="text-sm">{mascararIdentidade(desescaparEntidades(texto))}</p>
          <p className="text-xs text-muted-foreground">{quando}</p>
        </div>
        <button
          type="button"
          aria-label={aberto ? "Recolher" : "Expandir"}
          aria-expanded={aberto}
          className="rounded p-1 hover:bg-muted"
          onClick={() => {
            setAberto((v) => !v);
            if (!n.is_read) onLer(n.id);
          }}
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${aberto ? "rotate-180" : ""}`} />
        </button>
      </div>
      {aberto && (
        <div className="mt-2 space-y-1 border-t pt-2 text-sm" data-testid="notificacao-detalhe">
          {n.mensagem && n.titulo &&
            (n.tipo === "handoff" || n.tipo === "julia_handoff" ? (
              <HandoffDetalhe mensagem={n.mensagem} />
            ) : (
              <p>{mascararIdentidade(desescaparEntidades(n.mensagem))}</p>
            ))}
          {n.link && <a href={n.link} className="text-primary underline">Abrir</a>}
        </div>
      )}
    </li>
  );
}
