/**
 * ImovelDivergenciasVista — "Divergências com o Vista": where the Vista
 * mirror and OUR data disagree about the same fact, a human decides.
 *
 * TRANSITIONAL and REMOVABLE (owner, 2026-11-04): everything for this feature
 * is this file + `hooks/useImovelDivergencias.ts` + one mount and one
 * `rowBadge` prop in `ImovelDetalhes`. The sync never overwrites; it flags.
 *
 * Why not `ConflitosPendentesCard` (the existing imóvel/cliente conflict
 * card): that decision is binary (accept the proposed reading / reject), this
 * one is three-way (Vista / ours / a corrected value) and shows the ORIGIN of
 * our value (a Julia conversation). It reuses that card's field-label seam
 * (`rotuloCampoImovel`) and its admin-only-buttons posture.
 *
 * States: nothing pending ⇒ the block does not render (almost every page);
 * first load ⇒ nothing (a skeleton would flash on every page); a failed read
 * is an error card with retry, never silence; a resolve refusal is drawn on
 * the item. History is collapsed. Read is open, buttons are org-admin (UX
 * only — the server enforces).
 */
import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Loader2, MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";

import { isOrgAdmin } from "@noctusai/lib";
import { MirrorOverrideValue } from "@noctusai/lib/components";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  pendentesDoCampo,
  useImovelDivergencias,
  useResolverDivergencia,
  type Divergencia,
} from "@/hooks/useImovelDivergencias";
import { JULIA_PAGES } from "@/nav/julia";

import { rotuloCampoImovel } from "./ImovelConflitosCard";

const ROTULOS_EXTRA: Record<string, string> = {
  valor_venda: "Valor de venda",
  valor_locacao: "Valor de locação",
  valor_condominio: "Condomínio",
  valor_iptu: "IPTU",
  area_terreno: "Área do terreno",
  area_terreno_m2: "Área do terreno",
  area_construida: "Área construída",
  area_construida_m2: "Área construída",
  dormitorios: "Dormitórios",
  suites: "Suítes",
  vagas: "Vagas",
  status: "Status",
};

const rotulo = (campo: string) => ROTULOS_EXTRA[campo] ?? rotuloCampoImovel(campo);

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function data(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("pt-BR") : "";
}

function Origem({ d }: { d: Divergencia }) {
  const o = d.origem;
  if (!o) return null;
  return (
    <div className="space-y-0.5 text-xs text-muted-foreground" data-testid={`divergencia-${d.id}-origem`}>
      {o.tipo === "julia" && o.contato_id ? (
        <Link
          to={`${JULIA_PAGES.conversas.href}/h/${encodeURIComponent(o.contato_id)}`}
          className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-foreground"
          data-testid={`divergencia-${d.id}-conversa`}
        >
          <MessageSquare className="h-3 w-3" />
          Ver a conversa que definiu o nosso valor
        </Link>
      ) : (
        <span>Origem: {o.tipo}</span>
      )}
      {o.trecho && <p className="italic">“{o.trecho}”</p>}
    </div>
  );
}

function Item({ d, codigo, isAdmin }: { d: Divergencia; codigo: string; isAdmin: boolean }) {
  const resolver = useResolverDivergencia(codigo);
  const [corrigindo, setCorrigindo] = useState(false);
  const [valor, setValor] = useState("");
  const pendente = d.status === "pendente";
  const ocupado = resolver.isPending;

  return (
    <li className="space-y-2 py-3" data-testid={`divergencia-${d.id}`}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{rotulo(d.campo)}</span>
        {!pendente && d.resolucao && (
          <Badge variant="outline" data-testid={`divergencia-${d.id}-resolucao`}>
            {{ vista: "Usou o Vista", nosso: "Manteve o nosso", manual: "Corrigido" }[d.resolucao.escolha]}
          </Badge>
        )}
      </div>
      <div className="text-sm" data-testid={`divergencia-${d.id}-valores`}>
        <MirrorOverrideValue mirror={fmt(d.valor_vista)} owned={fmt(d.valor_nosso)} />
      </div>
      <p className="text-xs text-muted-foreground">
        Vista{d.vista_em ? ` em ${data(d.vista_em)}` : ""} · Nosso
        {d.nosso_em ? ` em ${data(d.nosso_em)}` : ""}
        {d.nosso_por?.nome ? ` por ${d.nosso_por.nome}` : ""}
      </p>
      <Origem d={d} />

      {pendente && isAdmin && (
        <div className="space-y-2">
          {corrigindo ? (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (valor.trim()) resolver.mutate({ id: d.id, escolha: "manual", valor: valor.trim() });
              }}
            >
              <Input
                value={valor}
                onChange={(e) => setValor(e.target.value)}
                aria-label={`Valor correto de ${rotulo(d.campo)}`}
                data-testid={`divergencia-${d.id}-valor`}
                disabled={ocupado}
              />
              <Button type="submit" size="sm" disabled={ocupado || !valor.trim()} data-testid={`divergencia-${d.id}-corrigir-salvar`}>
                Salvar
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={ocupado} onClick={() => setCorrigindo(false)}>
                Cancelar
              </Button>
            </form>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={ocupado}
                onClick={() => resolver.mutate({ id: d.id, escolha: "vista" })}
                data-testid={`divergencia-${d.id}-usar-vista`}
              >
                {ocupado && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                Usar Vista
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={ocupado}
                onClick={() => resolver.mutate({ id: d.id, escolha: "nosso" })}
                data-testid={`divergencia-${d.id}-manter-nosso`}
              >
                Manter o nosso
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={ocupado}
                onClick={() => setCorrigindo(true)}
                data-testid={`divergencia-${d.id}-corrigir`}
              >
                Corrigir
              </Button>
            </div>
          )}
          {resolver.error && (
            <p className="text-sm text-destructive" role="alert" data-testid={`divergencia-${d.id}-erro`}>
              {resolver.error.message}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export function ImovelDivergenciasVista({ codigo }: { codigo: string }) {
  const query = useImovelDivergencias(codigo);
  const ssoCtx = useEffectiveSSOContext();
  const isAdmin = isOrgAdmin(ssoCtx);
  const [verHistorico, setVerHistorico] = useState(false);

  if (query.isError && !query.data) {
    return (
      <Card data-testid="imovel-divergencias-erro">
        <CardContent className="flex flex-col items-center gap-3 p-6 text-center">
          <p className="text-sm text-muted-foreground">
            Não foi possível carregar as divergências com o Vista.
          </p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  const itens = query.data ?? [];
  const pendentes = itens.filter((d) => d.status === "pendente");
  const historico = itens.filter((d) => d.status !== "pendente");
  // Only exists while there is something to decide.
  if (pendentes.length === 0) return null;

  return (
    <Card id="imovel-divergencias" data-testid="imovel-divergencias">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          Divergências com o Vista
          <Badge data-testid="imovel-divergencias-contagem">{pendentes.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">
          O Vista e os nossos dados dizem coisas diferentes. A sincronização não sobrescreve nada:
          {isAdmin ? " escolha qual é o certo." : " um administrador da organização decide qual é o certo."}
        </p>
        <ul className="divide-y">
          {pendentes.map((d) => (
            <Item key={d.id} d={d} codigo={codigo} isAdmin={isAdmin} />
          ))}
        </ul>
        {historico.length > 0 && (
          <div>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setVerHistorico((v) => !v)}
              aria-expanded={verHistorico}
              data-testid="imovel-divergencias-historico-toggle"
            >
              {verHistorico ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Histórico ({historico.length})
            </button>
            {verHistorico && (
              <ul className="divide-y" data-testid="imovel-divergencias-historico">
                {historico.map((d) => (
                  <Item key={d.id} d={d} codigo={codigo} isAdmin={isAdmin} />
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** A count badge for a field row that diverges (`campos` = the names the
 *  backend may use for that fact). Renders nothing at zero. */
export function DivergenciaCampoBadge({ codigo, campos }: { codigo: string; campos: readonly string[] }) {
  const query = useImovelDivergencias(codigo);
  const n = pendentesDoCampo(query.data, campos);
  if (n === 0) return null;
  return (
    <a href="#imovel-divergencias" className="ml-1 inline-flex" title="Diverge do Vista — ver divergências">
      <Badge variant="outline" className="border-amber-500 text-amber-700" data-testid={`divergencia-badge-${campos[0]}`}>
        {n}
      </Badge>
    </a>
  );
}
