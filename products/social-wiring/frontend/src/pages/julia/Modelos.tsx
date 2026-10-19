/** Julia › Modelos de mensagem (`/julia/modelos`) — contract §14 W12. */
import { useMemo, useState } from "react";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, Plus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ModeloCard } from "@/components/julia/modelos/ModeloCard";
import { ModeloPreviewDrawer } from "@/components/julia/modelos/ModeloPreviewDrawer";
import { NovoModeloModal } from "@/components/julia/modelos/NovoModeloModal";
import { CATEGORIAS, MODELOS_KEY, useModelos, type Modelo } from "@/hooks/useJuliaModelos";

export default function JuliaModelos() {
  const qc = useQueryClient();
  const { data, isPending, isError, refetch } = useModelos();
  const refreshing = useIsFetching({ queryKey: MODELOS_KEY }) > 0 && !!data;
  const [busca, setBusca] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [novo, setNovo] = useState(false);
  const [aberto, setAberto] = useState<Modelo | null>(null);

  const contagem = useMemo(() => {
    const m: Record<string, number> = {};
    for (const x of data ?? []) m[x.categoria] = (m[x.categoria] ?? 0) + 1;
    return m;
  }, [data]);
  const filtrados = (data ?? []).filter(
    (m) => (!cat || m.categoria === cat) && (!busca || `${m.nome} ${m.conteudo}`.toLowerCase().includes(busca.toLowerCase())),
  );
  const showSkeleton = isPending && !data;

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Modelos de mensagem</h1>
          <p className="text-sm text-muted-foreground">Crie e gerencie os modelos usados nos disparos e no reengajamento.</p>
        </div>
        <div className="flex items-center gap-2">
          {refreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="modelos-refreshing" />}
          <Button variant="outline" size="icon" aria-label="Atualizar" onClick={() => qc.invalidateQueries({ queryKey: MODELOS_KEY })}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => setNovo(true)}>
            <Plus className="mr-1 h-4 w-4" /> Criar modelo de mensagem
          </Button>
        </div>
      </header>

      <Input placeholder="Buscar modelo" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar modelo" />
      <div className="flex flex-wrap gap-2">
        {CATEGORIAS.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={cat === c}
            onClick={() => setCat(cat === c ? null : c)}
            className={`rounded-full border px-3 py-1 text-xs ${cat === c ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            {c} ({contagem[c] ?? 0})
          </button>
        ))}
      </div>

      {showSkeleton ? (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="modelos-skeleton">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : isError && !data ? (
        <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Não foi possível carregar os modelos.
          <Button variant="link" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : filtrados.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground" data-testid="modelos-vazio">
          {data?.length ? "Nenhum modelo encontrado." : "Nenhum modelo criado ainda. Crie o primeiro modelo de mensagem."}
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {filtrados.map((m) => (
            <ModeloCard key={m.id} modelo={m} onOpen={setAberto} />
          ))}
        </div>
      )}

      <NovoModeloModal open={novo} onOpenChange={setNovo} />
      <ModeloPreviewDrawer key={aberto?.id ?? "_"} modelo={aberto} onClose={() => setAberto(null)} />
    </div>
  );
}
