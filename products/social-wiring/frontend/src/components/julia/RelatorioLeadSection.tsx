/** Lead card: "Imóveis oferecidos" chips (código -> link, new tab) + "Relatório da Julia" (latest + older collapsed). */
import { Badge } from "@/components/ui/badge";
import { imoveisOferecidos, useJuliaRelatorios, type EnvioStatus, type TipoRelatorio } from "@/hooks/useJuliaRelatorioLead";

const TIPO: Record<TipoRelatorio, string> = { handoff: "Passagem para humano", conclusao: "Conclusão", alerta: "Alerta" };
const ENVIO: Record<EnvioStatus, string> = {
  pendente: "Envio pendente",
  enviado: "Enviado",
  falhou: "Falha no envio",
  sem_destino: "Sem destino",
};

function quando(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function ImoveisOferecidosChips({ payload }: { payload: unknown }) {
  const itens = imoveisOferecidos(payload);
  if (itens.length === 0) return null;
  return (
    <section className="space-y-1" data-testid="imoveis-oferecidos">
      <h4 className="text-xs font-medium text-muted-foreground">Imóveis oferecidos</h4>
      <ul className="flex flex-wrap gap-1">
        {itens.map((i) => (
          <li key={i.codigo}>
            {i.link ? (
              <a href={i.link} target="_blank" rel="noopener noreferrer" data-testid={`imovel-chip-${i.codigo}`}>
                <Badge variant="outline" className="hover:bg-muted">{i.codigo}</Badge>
              </a>
            ) : (
              <Badge variant="secondary" data-testid={`imovel-chip-${i.codigo}`}>{i.codigo}</Badge>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RelatorioLeadSection({ contatoId }: { contatoId: string | null }) {
  const q = useJuliaRelatorios(contatoId);
  if (!contatoId) return null;
  if (q.isPending && !q.data) return <div className="h-16 animate-pulse rounded bg-muted" data-testid="relatorio-skeleton" />;
  if (!q.data) {
    return (
      <p role="alert" className="text-xs text-destructive" data-testid="relatorio-erro">
        Não foi possível carregar os relatórios da Julia.
      </p>
    );
  }
  const [ultimo, ...antigos] = q.data;
  return (
    <section className="space-y-2" data-testid="relatorio-julia">
      <h4 className="text-xs font-medium text-muted-foreground">Relatório da Julia</h4>
      {!ultimo ? (
        <p className="text-xs text-muted-foreground" data-testid="relatorio-vazio">
          A Julia ainda não gerou relatório para este lead.
        </p>
      ) : (
        <Relatorio r={ultimo} destaque />
      )}
      {antigos.length > 0 && (
        <details data-testid="relatorios-anteriores">
          <summary className="cursor-pointer text-xs text-muted-foreground">Relatórios anteriores ({antigos.length})</summary>
          <div className="mt-2 space-y-3">
            {antigos.map((r) => (
              <Relatorio key={r.id} r={r} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function Relatorio({ r, destaque = false }: { r: import("@/hooks/useJuliaRelatorioLead").RelatorioJulia; destaque?: boolean }) {
  return (
    <article className="space-y-1 rounded-md border p-2" data-testid={destaque ? "relatorio-ultimo" : `relatorio-${r.id}`}>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <Badge variant={r.tipo === "alerta" ? "destructive" : "secondary"}>{TIPO[r.tipo] ?? r.tipo}</Badge>
        <Badge variant={r.envio_status === "falhou" || r.envio_status === "sem_destino" ? "destructive" : "outline"}>
          {ENVIO[r.envio_status] ?? r.envio_status}
        </Badge>
        <span className="text-muted-foreground">{quando(r.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap text-sm" data-testid="relatorio-texto">{r.texto}</p>
      {r.envio_erro && <p className="text-xs text-destructive">{r.envio_erro}</p>}
    </article>
  );
}
