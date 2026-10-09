/**
 * ClientesExcluidosPanel — admin-only "Excluídos" view of `/clientes`.
 * Lists deleted people (tombstones on their lead sources) and lets an
 * admin/owner restore one. The caller mounts it only for org admins; the
 * server enforces (403) regardless.
 */
import { useState } from "react";
import { AlertCircle, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useClientesExcluidos,
  useRestaurarClienteExcluido,
  type ClienteExcluido,
} from "@/hooks/useClientes";
import { toastServerError } from "@/lib/erroServidor";
import { RestaurarClienteConfirmDialog } from "./RestaurarClienteConfirmDialog";

function formatarData(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function ClientesExcluidosPanel() {
  const navigate = useNavigate();
  const lista = useClientesExcluidos();
  const restaurar = useRestaurarClienteExcluido();
  const [alvo, setAlvo] = useState<ClienteExcluido | null>(null);

  const showSkeleton = lista.isPending && !lista.data;
  const isRefreshing = lista.isFetching && !!lista.data;
  const items = lista.data?.items ?? [];

  function confirmar() {
    if (!alvo) return;
    restaurar.mutate(alvo.cliente_id, {
      onSuccess: (res) => {
        setAlvo(null);
        const novoId = res.cliente_id;
        toast.success("Cliente restaurado", novoId
          ? {
              action: {
                label: "Abrir cliente",
                onClick: () => navigate(`/clientes/${novoId}`),
              },
            }
          : undefined);
      },
      onError: (err) => {
        setAlvo(null);
        toastServerError(err, "Não foi possível restaurar o cliente.");
      },
    });
  }

  if (lista.isError && !lista.data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <AlertCircle className="h-10 w-10 text-destructive" />
          <p className="font-medium">Não foi possível carregar os clientes excluídos.</p>
          <Button variant="outline" onClick={() => lista.refetch()}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (showSkeleton) {
    return (
      <div className="space-y-2" data-testid="excluidos-skeleton">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <>
      {items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Trash2 className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Nenhum cliente excluído.</p>
          </CardContent>
        </Card>
      ) : (
        <Card aria-busy={isRefreshing}>
          <CardContent className="p-0">
            <table className="w-full text-sm" data-testid="excluidos-tabela">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="p-3 font-medium">Cliente</th>
                  <th className="p-3 font-medium">Excluído por</th>
                  <th className="p-3 font-medium">Excluído em</th>
                  <th className="p-3 font-medium">Origens</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.cliente_id} className="border-b last:border-0" data-testid="excluido-row">
                    <td className="p-3">{c.cliente_nome || "Sem nome"}</td>
                    <td className="p-3">{c.excluido_por_nome || "—"}</td>
                    <td className="p-3">{formatarData(c.excluido_em)}</td>
                    <td className="p-3">{c.origens} lead(s)</td>
                    <td className="p-3 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAlvo(c)}
                        data-testid="restaurar-btn"
                      >
                        Restaurar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <RestaurarClienteConfirmDialog
        open={!!alvo}
        pending={restaurar.isPending}
        nome={alvo?.cliente_nome ?? ""}
        onOpenChange={(o) => {
          if (!o) setAlvo(null);
        }}
        onConfirm={confirmar}
      />
    </>
  );
}
