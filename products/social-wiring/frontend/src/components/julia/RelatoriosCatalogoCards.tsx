/** Julia › Agente — "Relatórios e alertas" (where the report goes) and "Catálogo de imóveis" (Vista live | local mirror). */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { env } from "@noctusai/lib";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useTeamMembers } from "@/hooks/useTeam";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import {
  useCatalogoFonte,
  useRelatorioDestino,
  useSalvarCatalogoFonte,
  useSalvarRelatorioDestino,
  type FonteCatalogo,
  type ModoRelatorioDestino,
} from "@/hooks/useJuliaRelatorioLead";

function Esqueleto({ testId }: { testId: string }) {
  return <div className="h-32 animate-pulse rounded-lg bg-muted" data-testid={testId} />;
}

function ErroCard({ titulo, testId, onRetry }: { titulo: string; testId: string; onRetry: () => void }) {
  return (
    <Card data-testid={testId}>
      <CardContent className="flex items-center justify-between gap-3 py-6">
        <p role="alert" className="text-sm text-destructive">
          Não foi possível carregar: {titulo}.
        </p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Tentar de novo
        </Button>
      </CardContent>
    </Card>
  );
}

export function RelatoriosCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useRelatorioDestino();
  const team = useTeamMembers();
  const salvar = useSalvarRelatorioDestino();
  const [erro, setErro] = useState<string | null>(null);

  if (q.isPending && !q.data) return <Esqueleto testId="relatorios-skeleton" />;
  if (!q.data) return <ErroCard titulo="destino dos relatórios" testId="relatorios-erro" onRetry={() => q.refetch()} />;

  const d = q.data;
  const membros = (team.data ?? []).map((m) => ({ id: m.id, nome: m.nome || m.email }));
  const fora = !!d.usuario_id && !membros.some((m) => m.id === d.usuario_id);

  function enviar(modo: ModoRelatorioDestino, usuario_id: string | null) {
    setErro(null);
    const usuario_nome = membros.find((m) => m.id === usuario_id)?.nome ?? null;
    salvar.mutate(
      { modo, usuario_id, usuario_nome },
      {
        onSuccess: () => toast.success("Destino dos relatórios salvo"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar o destino dos relatórios.")),
      },
    );
  }

  return (
    <Card data-testid="relatorios-card">
      <CardHeader>
        <CardTitle className="text-base">Relatórios e alertas</CardTitle>
        <CardDescription>
          Quando a Julia passa um lead para uma pessoa (ou algo dá errado) ela envia um relatório por WhatsApp. Escolha
          quem recebe; o WhatsApp vem do cadastro da pessoa no noc. O relatório também fica salvo no card do lead.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2" disabled={!isAdmin || salvar.isPending}>
          <legend className="sr-only">Destino dos relatórios</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="rel-modo" checked={d.modo === "usuario"} onChange={() => enviar("usuario", d.usuario_id)} />
            Um usuário da empresa
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="rel-modo" checked={d.modo === "responsavel"} onChange={() => enviar("responsavel", d.usuario_id)} />
            Responsável do lead
          </label>
          {d.modo === "responsavel" && (
            <p className="text-xs text-muted-foreground">
              Vai para o WhatsApp do responsável pelo lead; se ele não tiver WhatsApp, usa o usuário abaixo.
            </p>
          )}
        </fieldset>
        <div className="space-y-1">
          <Label htmlFor="rel-usuario">{d.modo === "usuario" ? "Quem recebe os relatórios" : "Usuário reserva"}</Label>
          <select
            id="rel-usuario"
            className="flex h-9 w-full max-w-xs rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
            value={d.usuario_id ?? ""}
            disabled={!isAdmin || salvar.isPending}
            onChange={(e) => enviar(d.modo, e.target.value || null)}
          >
            <option value="">Selecione…</option>
            {fora && <option value={d.usuario_id!}>{d.usuario_nome ?? "Usuário configurado (fora da lista)"}</option>}
            {membros.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nome}
              </option>
            ))}
          </select>
          {team.isError && (
            <p className="text-xs text-muted-foreground" data-testid="rel-membros-erro">
              Não foi possível listar os membros da empresa.
            </p>
          )}
          {d.usuario_id &&
            (d.telefone_resolvido ? (
              <p className="text-xs text-muted-foreground" data-testid="rel-telefone">
                WhatsApp (do noc): {d.telefone_resolvido}
              </p>
            ) : (
              <p className="text-xs text-warning-foreground" data-testid="rel-sem-whatsapp">
                Sem WhatsApp — cadastre no noc.{" "}
                <a href={`${env.CORE_URL.replace(/\/$/, "")}/settings`} target="_blank" rel="noopener noreferrer" className="underline">
                  Abrir configurações da conta
                </a>
              </p>
            ))}
        </div>
        {salvar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {erro && (
          <p role="alert" className="text-sm text-destructive" data-testid="relatorios-salvar-erro">
            {erro}
          </p>
        )}
        {!isAdmin && <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>}
      </CardContent>
    </Card>
  );
}

export function CatalogoCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useCatalogoFonte();
  const salvar = useSalvarCatalogoFonte();
  const [erro, setErro] = useState<string | null>(null);

  if (q.isPending && !q.data) return <Esqueleto testId="catalogo-skeleton" />;
  if (!q.data) return <ErroCard titulo="fonte do catálogo" testId="catalogo-erro" onRetry={() => q.refetch()} />;

  function escolher(fonte: FonteCatalogo) {
    if (fonte === q.data?.fonte) return;
    setErro(null);
    salvar.mutate(
      { fonte },
      {
        onSuccess: () => toast.success("Fonte do catálogo atualizada"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar a fonte do catálogo.")),
      },
    );
  }

  return (
    <Card data-testid="catalogo-card">
      <CardHeader>
        <CardTitle className="text-base">Catálogo de imóveis</CardTitle>
        <CardDescription>De onde a Julia busca os imóveis que oferece aos leads.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <fieldset className="space-y-2" disabled={!isAdmin || salvar.isPending}>
          <legend className="sr-only">Fonte do catálogo</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="cat-fonte" checked={q.data.fonte === "vista"} onChange={() => escolher("vista")} />
            Vista (ao vivo)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="cat-fonte" checked={q.data.fonte === "espelho"} onChange={() => escolher("espelho")} />
            Espelho local
          </label>
        </fieldset>
        {salvar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {erro && (
          <p role="alert" className="text-sm text-destructive" data-testid="catalogo-salvar-erro">
            {erro}
          </p>
        )}
        {!isAdmin && <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>}
      </CardContent>
    </Card>
  );
}
