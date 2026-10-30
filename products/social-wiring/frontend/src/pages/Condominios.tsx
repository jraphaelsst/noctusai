/**
 * Condomínios — the master list the price evaluator keys location on
 * (migration 265).
 *
 * Built FROM data ("Gerar sugestões" clusters the Vista `empreendimento`
 * spellings), then refined and VALIDATED here by the owner; once validated the
 * list is the permanent source of truth. Suggestions never overwrite a
 * validated row.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Building, Loader2, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";

import { useEffectiveSSOContext } from "@noctusai/lib/design-system";
import { isOrgAdmin } from "@noctusai/lib";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CondominioDetalhe } from "@/components/condominios/CondominioDetalhe";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  STATUS_LABELS,
  type StatusValidacao,
  useCondominios,
  useSugerirCondominios,
} from "@/hooks/useCondominios";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

const STATUS_CLASSE: Record<StatusValidacao, string> = {
  sugerido: "bg-warning/15 text-warning-foreground",
  validado: "bg-success/15 text-success",
  descartado: "bg-muted text-muted-foreground",
};

function erro(e: unknown, fallback: string): string {
  const msg = (e as { message?: string } | null)?.message;
  return msg && msg.trim() ? msg : fallback;
}

export default function Condominios() {
  const ssoCtx = useEffectiveSSOContext();
  const admin = isOrgAdmin(ssoCtx);

  const [status, setStatus] = useState<StatusValidacao | "">("");
  const [cidade, setCidade] = useState("");
  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca);
  const [aberto, setAberto] = useState<string | null>(null);

  const lista = useCondominios({ status, cidade, q });
  const todos = useCondominios();
  const sugerir = useSugerirCondominios();

  // Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = lista.isPending && !lista.data;
  const isRefreshing = lista.isFetching && !!lista.data;
  const itens = lista.data ?? [];

  const cidades = useMemo(
    () =>
      Array.from(new Set((todos.data ?? []).map((c) => c.cidade).filter((c): c is string => !!c))).sort(
        (a, b) => a.localeCompare(b, "pt-BR"),
      ),
    [todos.data],
  );

  function gerar() {
    sugerir.mutate(undefined, {
      onSuccess: (r) =>
        toast.success(
          `${r.condominios_criados} condomínio(s) sugerido(s), ${r.aliases_novos} grafia(s) nova(s).`,
        ),
      onError: (e) => toast.error(erro(e, "Não foi possível gerar sugestões.")),
    });
  }

  return (
    <div className="space-y-4 p-6" data-testid="condominios-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Building className="h-6 w-6" /> Condomínios
          </h1>
          <p className="text-sm text-muted-foreground">
            Lista mestra usada pelo avaliador de preço. Valide as sugestões para torná-las a fonte da verdade.
          </p>
        </div>
        {admin && (
          <Button onClick={gerar} disabled={sugerir.isPending}>
            {sugerir.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            Gerar sugestões
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="w-64"
          placeholder="Buscar por nome"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          aria-label="Buscar condomínio"
        />
        <select
          className="h-9 rounded-md border bg-background px-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusValidacao | "")}
          aria-label="Filtrar por status"
        >
          <option value="">Todos os status</option>
          {(Object.keys(STATUS_LABELS) as StatusValidacao[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border bg-background px-2 text-sm"
          value={cidade}
          onChange={(e) => setCidade(e.target.value)}
          aria-label="Filtrar por cidade"
        >
          <option value="">Todas as cidades</option>
          {cidades.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        {isRefreshing && <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />}
      </div>

      {lista.isError && !lista.data && (
        <Card>
          <CardContent className="flex items-center gap-2 p-4 text-sm text-destructive" role="alert">
            <TriangleAlert className="h-4 w-4" />
            {erro(lista.error, "Não foi possível carregar os condomínios.")}
            <Button size="sm" variant="outline" onClick={() => lista.refetch()}>
              Tentar de novo
            </Button>
          </CardContent>
        </Card>
      )}

      {showSkeleton && (
        <div className="space-y-2" data-testid="condominios-skeleton">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {!showSkeleton && !lista.isError && itens.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground" data-testid="condominios-vazio">
            {status || cidade || q
              ? "Nenhum condomínio com esses filtros."
              : admin
                ? "Nenhum condomínio ainda. Use “Gerar sugestões” para montar a lista a partir do Vista."
                : "Nenhum condomínio ainda. Um administrador pode gerar as sugestões."}
          </CardContent>
        </Card>
      )}

      {itens.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Nome</th>
                <th className="px-3 py-2">Cidade / bairro</th>
                <th className="px-3 py-2 text-right">Imóveis</th>
                <th className="px-3 py-2 text-right">Preço/m² mediano</th>
                <th className="px-3 py-2 text-right">Grafias</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((c) => (
                <tr
                  key={c.id}
                  className="cursor-pointer border-t hover:bg-muted/40"
                  onClick={() => setAberto(c.id)}
                  data-testid={`condominio-linha-${c.id}`}
                >
                  <td className="px-3 py-2 font-medium">{c.nome}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {[c.cidade, c.bairro].filter(Boolean).join(" / ") || "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{c.imoveis_count}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {c.preco_m2_mediano == null ? "—" : BRL.format(c.preco_m2_mediano)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{c.aliases_count}</td>
                  <td className="px-3 py-2">
                    <Badge className={STATUS_CLASSE[c.status_validacao]}>{STATUS_LABELS[c.status_validacao]}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CondominioDetalhe condominioId={aberto} todos={todos.data ?? []} onClose={() => setAberto(null)} />
    </div>
  );
}
