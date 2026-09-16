/**
 * Edição de Fotos — Curadores (`/edicao-fotos/curadores`, `status_pagina`
 * row `edicao-fotos-curadores`, migration 128). Grants/revokes the
 * `photo_curator` permission (Core `public.user_permission_grants`,
 * `noctusai_lib.domain.permissions`) — platform admin ONLY (contract §1:
 * "curators manage the platform-scope reference pool and guides, so
 * granting one is a platform decision"), never an agency admin.
 *
 * Gate: `dashboard === "platform"` — the sharpest signal `Capacidades` (§2)
 * carries for platform-admin-only surfaces (same inference `Configuracoes.
 * tsx` documents for its own admin/non-admin split; there is no dedicated
 * `pode_gerir_curadores` field). A curator themselves has `dashboard ===
 * null` (they are not an agency admin) and is correctly refused here — a
 * curator manages the pool/guides, never who else is a curator.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` /
 * `isRefreshing` come pre-computed off `useCuradores()` — never `.isLoading`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AlertCircle, Lock, ShieldCheck, Trash2, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@noctusai/lib/api";

import {
  fotosPermissions,
  useAdicionarCurador,
  useCapacidades,
  useCuradores,
  useRemoverCurador,
  type Curador,
} from "@/hooks/useEdicaoFotos";

function mensagemErro(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.code === "usuario_nao_encontrado") {
    return "Nenhum usuário com esse id foi encontrado.";
  }
  return err instanceof Error ? err.message : fallback;
}

export default function Curadores() {
  const { capacidades, showSkeleton: capsCarregando } = useCapacidades();
  const ehPlataforma = fotosPermissions.dashboardScope(capacidades) === "platform";

  if (capsCarregando) return <PageSkeleton />;
  if (!ehPlataforma) return <AcessoRestrito />;
  return <CuradoresView />;
}

function CuradoresView() {
  const { curadores, total, showSkeleton, isRefreshing, error, refetch } = useCuradores();
  const adicionar = useAdicionarCurador();
  const remover = useRemoverCurador();
  const [userId, setUserId] = useState("");

  async function handleAdicionar(e: FormEvent) {
    e.preventDefault();
    const id = userId.trim();
    if (!id) return;
    try {
      await adicionar.mutateAsync({ user_id: id });
      toast.success("Curador adicionado.");
      setUserId("");
    } catch (err) {
      toast.error("Não foi possível adicionar o curador.", { description: mensagemErro(err, "") });
    }
  }

  async function handleRemover(curador: Curador) {
    try {
      await remover.mutateAsync(curador.user_id);
      toast.success("Curador removido.");
    } catch (err) {
      toast.error("Não foi possível remover o curador.", { description: mensagemErro(err, "") });
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Curadores</h1>
          <p className="text-sm text-muted-foreground">
            Quem, além dos administradores da plataforma, pode gerir o pool de referências e os
            guias de estilo.
          </p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="curadores-atualizando">
            Atualizando…
          </span>
        )}
      </div>

      <Card>
        <CardContent className="p-4">
          <form className="flex flex-wrap items-end gap-3" onSubmit={handleAdicionar} data-testid="novo-curador-form">
            <div className="space-y-1.5">
              <Label htmlFor="curador-user-id">Id do usuário (NoctusAI)</Label>
              <Input
                id="curador-user-id"
                placeholder="uuid do usuário"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                className="w-80"
              />
            </div>
            <Button type="submit" disabled={!userId.trim() || adicionar.isPending}>
              <UserPlus className="mr-2 h-4 w-4" />
              {adicionar.isPending ? "Adicionando…" : "Adicionar curador"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <ListSkeleton />
      ) : curadores.length === 0 ? (
        <Card data-testid="curadores-vazio">
          <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
            <ShieldCheck className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Nenhum curador ainda.</p>
            <p className="text-sm text-muted-foreground">Adicione o id de um usuário acima para conceder curadoria.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y p-0" data-testid="curadores-lista">
            {curadores.map((curador) => (
              <div key={curador.user_id} className="flex items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-medium">{curador.nome ?? curador.user_id}</p>
                  <p className="text-sm text-muted-foreground">{curador.email ?? "—"}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRemover(curador)}
                  disabled={remover.isPending && remover.variables === curador.user_id}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {remover.isPending && remover.variables === curador.user_id ? "Removendo…" : "Remover"}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {!showSkeleton && !error && (
        <p className="text-xs text-muted-foreground">{total} curador(es) no total.</p>
      )}
    </div>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="curadores-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da plataforma NoctusAI.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6" data-testid="curadores-carregando">
      <Skeleton className="h-8 w-1/3" />
      <ListSkeleton />
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3" data-testid="curadores-loading">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-14 w-full" announce={i === 0} />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os curadores.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
