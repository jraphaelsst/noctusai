/**
 * "Possíveis duplicados" (CONTRACT §8.6/§8.7) on `/imoveis/:codigo`: each
 * pendente pair side by side with the matched signals + score. "Não é o mesmo"
 * is permanent; "É o mesmo imóvel" (admin only — the server enforces 403)
 * LINKS the manual record to the Vista listing, nothing is moved.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  sinalLabel,
  useDescartarDuplicata,
  useDuplicatasPendentes,
  useVincularDuplicata,
  type Duplicata,
  type ImovelResumo,
} from "@/hooks/useImovelDuplicatas";
import { formatArea, formatValor } from "@/hooks/useImoveis";

function num(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function Lado({ titulo, r }: { titulo: string; r: ImovelResumo }) {
  const valor = num(r.valor_venda);
  const area = num(r.area_total);
  return (
    <div className="min-w-0 flex-1 space-y-1 rounded-md border p-3 text-sm">
      <p className="text-xs font-medium uppercase text-muted-foreground">{titulo}</p>
      {r.foto_destaque ? (
        <img
          src={r.foto_destaque}
          alt={r.titulo ?? r.codigo}
          className="aspect-[4/3] w-full rounded object-cover"
        />
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center rounded bg-muted text-xs text-muted-foreground">
          Sem foto
        </div>
      )}
      <Link to={`/imoveis/${encodeURIComponent(r.codigo)}`} className="font-medium underline">
        {r.codigo}
      </Link>
      <p className="truncate">{r.titulo ?? "Sem título"}</p>
      <p className="truncate text-muted-foreground">{r.endereco_resumo ?? "—"}</p>
      <p>{valor !== null ? formatValor(valor) : "—"}</p>
      <p>{area !== null ? formatArea(area) : "—"}</p>
    </div>
  );
}

export default function ImovelDuplicatasSection({
  codigo,
  temPendentes,
}: {
  codigo: string;
  /** From `Imovel.duplicatas_pendentes` — gates the query (no pair, no read). */
  temPendentes: boolean;
}) {
  const isAdmin = useIsOrgAdmin();
  const query = useDuplicatasPendentes(temPendentes);
  const descartar = useDescartarDuplicata();
  const vincular = useVincularDuplicata();
  const [confirmando, setConfirmando] = useState<
    { tipo: "descartar" | "vincular"; par: Duplicata } | null
  >(null);

  if (!temPendentes) return null;
  const showSkeleton = query.isPending && !query.data;
  const pares = (query.data ?? []).filter(
    (d) => d.manual.codigo === codigo || d.vista.codigo === codigo,
  );
  const isRefreshing = query.isFetching && !!query.data;

  async function confirmar() {
    if (!confirmando) return;
    const { tipo, par } = confirmando;
    setConfirmando(null);
    try {
      if (tipo === "descartar") {
        await descartar.mutateAsync(par.id);
        toast.success("Marcado como imóveis diferentes.");
      } else {
        const res = await vincular.mutateAsync(par.id);
        if (res?.legal?.status === "erro") {
          toast.warning(
            res.legal.mensagem ??
              "Vinculado, mas os dados legais não puderam ser atualizados.",
          );
        } else {
          toast.success("Imóveis vinculados.");
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Não foi possível concluir a ação.");
    }
  }

  const ocupado = descartar.isPending || vincular.isPending;

  return (
    <Card data-testid="imovel-duplicatas">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Possíveis duplicados
          {isRefreshing && <Loader2 className="h-3 w-3 animate-spin" />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {showSkeleton ? (
          <Skeleton className="h-40 w-full" />
        ) : query.isError && !query.data ? (
          <p className="text-sm text-destructive" data-testid="imovel-duplicatas-erro">
            Não foi possível carregar os possíveis duplicados.
          </p>
        ) : (
          pares.map((par) => (
            <div key={par.id} className="space-y-3" data-testid={`duplicata-${par.id}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold" data-testid="duplicata-score">
                  {Math.round(par.score * 100)}%
                </span>
                {par.sinais.map((s) => (
                  <span
                    key={s.sinal}
                    title={s.detalhe ?? undefined}
                    className="rounded-full border px-2 py-0.5 text-xs"
                    data-testid="duplicata-sinal"
                  >
                    {sinalLabel(s.sinal)}
                  </span>
                ))}
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Lado titulo="Cadastro manual" r={par.manual} />
                <Lado titulo="Anúncio Vista" r={par.vista} />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={ocupado}
                  onClick={() => setConfirmando({ tipo: "descartar", par })}
                  data-testid="duplicata-descartar"
                >
                  Não é o mesmo
                </Button>
                {isAdmin && (
                  <Button
                    type="button"
                    size="sm"
                    disabled={ocupado}
                    onClick={() => setConfirmando({ tipo: "vincular", par })}
                    data-testid="duplicata-vincular"
                  >
                    É o mesmo imóvel
                  </Button>
                )}
              </div>
            </div>
          ))
        )}
      </CardContent>

      <AlertDialog open={!!confirmando} onOpenChange={(o) => !o && setConfirmando(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmando?.tipo === "vincular" ? "É o mesmo imóvel?" : "Não é o mesmo imóvel?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmando?.tipo === "vincular"
                ? "Vincula o cadastro manual ao anúncio da Vista. Nada é movido: o cadastro manual mantém seu processo, pasta do Drive e documentos. Dá para desvincular depois."
                : "Este par não será sugerido novamente. Esta decisão é permanente."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmar} data-testid="duplicata-confirmar">
              Confirmar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
