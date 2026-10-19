/** Julia › Atualização de imóveis (`/julia/proprietarios`) — contract §14 W12. */
import { useState } from "react";
import { toast } from "sonner";
import { useIsFetching } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TransporteBadge } from "@/components/julia/TransporteBadge";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  PROPRIETARIOS_KEY,
  STATUS_LABEL,
  useProprietarios,
  textoConfirmacao,
  useSolicitarAtualizacao,
  type ProprietarioStatus,
} from "@/hooks/useJuliaProprietarios";
import { TRANSPORTE_EXPLICACAO, envioLiberado, mensagemErroTransporte } from "@/hooks/useJuliaTransporte";

export default function JuliaProprietarios() {
  const [status, setStatus] = useState("");
  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 300);
  const { data, isPending, isError, refetch } = useProprietarios(status, q);
  const refreshing = useIsFetching({ queryKey: PROPRIETARIOS_KEY }) > 0 && !!data;
  const solicitar = useSolicitarAtualizacao();
  const liberado = envioLiberado(data?.transporte);
  const showSkeleton = isPending && !data;

  function pedir(id: string) {
    solicitar.mutate(id, {
      onSuccess: () => toast.success("Solicitação enviada ao proprietário"),
      onError: (e) => toast.error(mensagemErroTransporte(e, "Não foi possível solicitar a atualização.")),
    });
  }

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <header>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Atualização de imóveis</h1>
          <TransporteBadge transporte={data?.transporte} />
          {refreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="proprietarios-refreshing" />}
        </div>
        <p className="text-sm text-muted-foreground">Conversas com proprietários para atualizar os imóveis anunciados.</p>
      </header>

      <div className="flex gap-2">
        <Input placeholder="Buscar proprietário ou imóvel" aria-label="Buscar" value={busca} onChange={(e) => setBusca(e.target.value)} />
        <select
          aria-label="Status"
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Todos os status</option>
          {(Object.keys(STATUS_LABEL) as ProprietarioStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      {!liberado && <p className="text-xs text-muted-foreground">{TRANSPORTE_EXPLICACAO}</p>}

      {showSkeleton ? (
        <Skeleton className="h-32" data-testid="proprietarios-skeleton" />
      ) : isError && !data ? (
        <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Não foi possível carregar os proprietários.
          <Button variant="link" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : (data?.items.length ?? 0) === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground" data-testid="proprietarios-vazio">
          Nenhum proprietário encontrado.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1">Proprietário</th>
              <th>Imóvel</th>
              <th>Status</th>
              <th>Confirmado pelo proprietário</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.items.map((p) => (
              <tr key={p.id} className="border-t" data-testid="proprietario-linha">
                <td className="py-2">{p.nome}</td>
                <td>{p.imovel_codigo ?? "—"}</td>
                <td>{STATUS_LABEL[p.status]}</td>
                <td data-testid="proprietario-confirmacao" className="text-xs text-muted-foreground">{textoConfirmacao(p) ?? "—"}</td>
                <td className="text-right">
                  <Button size="sm" variant="outline" disabled={!liberado || p.status === "parar" || solicitar.isPending} onClick={() => pedir(p.id)}>
                    Solicitar atualização
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
