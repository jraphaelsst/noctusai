/** Lais › Disparos em massa (`/lais/disparos`) — contract §14 W12. */
import { useState } from "react";
import { useIsFetching } from "@tanstack/react-query";
import { AlertCircle, Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DisparoDetalheDrawer } from "@/components/lais/disparos/DisparoDetalheDrawer";
import { NovoDisparoWizard } from "@/components/lais/disparos/NovoDisparoWizard";
import { TransporteBadge } from "@/components/lais/TransporteBadge";
import { DISPAROS_KEY, STATUS_LABEL, TIPO_LABEL, useDisparos, type Disparo, type DisparoStatus, type DisparoTipo } from "@/hooks/useLaisDisparos";

type Aba = "todos" | DisparoStatus;
const ABAS: { v: Aba; label: string; status?: DisparoStatus }[] = [
  { v: "todos", label: "Todos" },
  { v: "rascunho", label: "Rascunhos", status: "rascunho" },
  { v: "agendado", label: "Agendados", status: "agendado" },
  { v: "enviado", label: "Enviados", status: "enviado" },
  { v: "cancelado", label: "Cancelados", status: "cancelado" },
  { v: "erro", label: "Erros", status: "erro" },
];

function Secao({ titulo, itens, onOpen }: { titulo: string; itens: Disparo[]; onOpen: (d: Disparo) => void }) {
  if (!itens.length) return null;
  return (
    <section className="space-y-1">
      <h2 className="text-xs font-semibold uppercase text-muted-foreground">{titulo}</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="py-1">Nome</th>
            <th>Status</th>
            <th>Tipo</th>
            <th>Contatos</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((d) => (
            <tr key={d.id} className="cursor-pointer border-t hover:bg-muted/50" data-testid="disparo-linha" onClick={() => onOpen(d)}>
              <td className="py-2">{d.nome}</td>
              <td>{STATUS_LABEL[d.status]}</td>
              <td>{TIPO_LABEL[d.tipo]}</td>
              <td>{d.contatos}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function LaisDisparos() {
  const { data, isPending, isError, refetch } = useDisparos();
  const refreshing = useIsFetching({ queryKey: DISPAROS_KEY }) > 0 && !!data;
  const [aba, setAba] = useState<Aba>("todos");
  const [tipo, setTipo] = useState<"" | DisparoTipo>("");
  const [novo, setNovo] = useState(false);
  const [aberto, setAberto] = useState<Disparo | null>(null);

  const todos = (data?.items ?? []).filter((d) => !tipo || d.tipo === tipo);
  const count = (s?: DisparoStatus) => (s ? todos.filter((d) => d.status === s).length : todos.length);
  const visiveis = aba === "todos" ? todos : todos.filter((d) => d.status === aba);
  const por = (...s: DisparoStatus[]) => visiveis.filter((d) => s.includes(d.status));
  const showSkeleton = isPending && !data;

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">Disparos em massa</h1>
            <TransporteBadge transporte={data?.transporte} />
          </div>
          <p className="text-sm text-muted-foreground">Envie mensagens no WhatsApp para diversos contatos de uma vez.</p>
        </div>
        <div className="flex items-center gap-2">
          {refreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="disparos-refreshing" />}
          <select
            aria-label="Tipo"
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as "" | DisparoTipo)}
          >
            <option value="">Todos os tipos</option>
            {(Object.keys(TIPO_LABEL) as DisparoTipo[]).map((t) => (
              <option key={t} value={t}>
                {TIPO_LABEL[t]}
              </option>
            ))}
          </select>
          <Button onClick={() => setNovo(true)}>
            <Plus className="mr-1 h-4 w-4" /> Novo disparo
          </Button>
        </div>
      </header>

      <Tabs value={aba} onValueChange={(v) => setAba(v as Aba)}>
        <TabsList>
          {ABAS.map((a) => (
            <TabsTrigger key={a.v} value={a.v}>
              {a.label} ({count(a.status)})
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {showSkeleton ? (
        <Skeleton className="h-32" data-testid="disparos-skeleton" />
      ) : isError && !data ? (
        <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Não foi possível carregar os disparos.
          <Button variant="link" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : visiveis.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground" data-testid="disparos-vazio">
          Nenhum disparo por aqui. Crie um novo disparo para começar.
        </p>
      ) : (
        <div className="space-y-6">
          <Secao titulo="Rascunhos" itens={por("rascunho")} onOpen={setAberto} />
          <Secao titulo="Agendados" itens={por("agendado")} onOpen={setAberto} />
          <Secao titulo="Histórico" itens={por("enviado", "cancelado", "erro")} onOpen={setAberto} />
        </div>
      )}

      <NovoDisparoWizard open={novo} onOpenChange={setNovo} />
      <DisparoDetalheDrawer key={aberto?.id ?? "_"} disparo={aberto} transporte={data?.transporte} onClose={() => setAberto(null)} />
    </div>
  );
}
