/**
 * Guia de documentos (`/guia-documentos`, status_pagina `guia_documentos`).
 *
 * ONE place that answers, from the code catalogs (`GET /api/guia-documentos`):
 *   - Fluxo do lead      — each stage, in order, and what it demands;
 *   - Dados obrigatórios — the client checklist and which documents fill it;
 *   - Documentos         — what is read from each document and where it goes;
 *   - Certidões          — source, requirements, credential per certidão;
 *   - Busca por dado     — type a field, see the documents that supply it.
 *
 * Read-only by nature: the content is derived from code (no CRUD exists — the
 * catalogs change with a deploy, not with a click), so page-scoped CRUD does
 * not apply here.
 *
 * Deep links: `#documento-<tipo>`, `#certidao-<tipo>`, `#etapa-<chave>`,
 * `#campo-<campo>`, `#dado-<chave>` scroll to and briefly highlight the target
 * — the "Ver no guia" link in every card "i" lands here.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { FileText, KeyRound, Loader2, Search, ShieldCheck, UserRound } from "lucide-react";
import { QueryErrorState } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useGuiaDocumentos } from "@/hooks/useGuiaDocumentos";
import {
  ROTULO_FONTE_CERTIDAO,
  SECOES_GUIA,
  ancora,
  buscarCampos,
  requisitosCertidao,
  rotuloDocumento,
} from "@/lib/guiaDocumentos";
import { cn } from "@/lib/utils";
import type { GuiaDocumentos as Guia, GuiaEtapaExigencia } from "@/types/guiaDocumentos";

const DESTAQUE_MS = 2500;

/** Scrolls to `location.hash` once the content exists, and returns the id to
 *  highlight for a moment. Re-runs on every hash change (in-page links). */
function useAncoraDestacada(pronto: boolean): string | null {
  const { hash } = useLocation();
  const [destaque, setDestaque] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto || !hash) return;
    const id = decodeURIComponent(hash.slice(1));
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView?.({ behavior: "smooth", block: "start" });
    setDestaque(id);
    const t = window.setTimeout(() => setDestaque(null), DESTAQUE_MS);
    return () => window.clearTimeout(t);
  }, [pronto, hash]);

  return destaque;
}

function classeAncora(id: string, destaque: string | null) {
  return cn(
    "scroll-mt-20 rounded-md transition-shadow duration-500",
    destaque === id && "ring-2 ring-primary ring-offset-2 ring-offset-background",
  );
}

function hrefExigencia(e: GuiaEtapaExigencia): string {
  if (e.tipo === "documento") return `#${ancora.documento(e.ref)}`;
  if (e.tipo === "certidao") return `#${ancora.certidao(e.ref)}`;
  return `#${ancora.campo(e.ref)}`;
}

const ICONE_EXIGENCIA = { campo: UserRound, documento: FileText, certidao: ShieldCheck } as const;

function LinkDocumento({ guia, tipo }: { guia: Guia; tipo: string }) {
  return (
    <Link to={`#${ancora.documento(tipo)}`} className="text-primary hover:underline">
      {rotuloDocumento(guia, tipo)}
    </Link>
  );
}

function Secao({ id, titulo, descricao, children }: { id: string; titulo: string; descricao: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className="scroll-mt-20 space-y-3" data-testid={`guia-secao-${id}`}>
      <div>
        <h2 id={`${id}-titulo`} className="text-lg font-semibold">
          {titulo}
        </h2>
        <p className="text-sm text-muted-foreground">{descricao}</p>
      </div>
      {children}
    </section>
  );
}

function Vazio({ children }: { children: ReactNode }) {
  return <p className="text-sm italic text-muted-foreground">{children}</p>;
}

function FluxoDoLead({ guia, destaque }: { guia: Guia; destaque: string | null }) {
  if (guia.etapas.length === 0) return <Vazio>Nenhuma etapa definida.</Vazio>;
  return (
    <ol className="space-y-2" data-testid="guia-etapas">
      {guia.etapas.map((e, i) => {
        const id = ancora.etapa(e.chave);
        return (
          <li key={e.chave} id={id} className={classeAncora(id, destaque)} data-testid={`guia-etapa-${e.chave}`}>
            <Card>
              <CardContent className="flex gap-3 p-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{e.rotulo}</span>
                    {e.bloco && <Badge variant="secondary">{e.bloco}</Badge>}
                  </div>
                  {e.exige.length > 0 ? (
                    <ul className="flex flex-wrap gap-1.5">
                      {e.exige.map((x) => {
                        const Icone = ICONE_EXIGENCIA[x.tipo];
                        return (
                          <li key={`${x.tipo}-${x.ref}`}>
                            <Link
                              to={hrefExigencia(x)}
                              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:bg-muted"
                            >
                              <Icone className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                              {x.rotulo}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">Nada exigido nesta etapa.</p>
                  )}
                  {e.observacao && <p className="text-xs text-muted-foreground">{e.observacao}</p>}
                </div>
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ol>
  );
}

function DadosObrigatorios({ guia, destaque }: { guia: Guia; destaque: string | null }) {
  if (guia.dados_obrigatorios.length === 0) return <Vazio>Nenhum dado obrigatório definido.</Vazio>;
  return (
    <Card>
      <CardContent className="divide-y p-0" data-testid="guia-dados">
        {guia.dados_obrigatorios.map((d) => {
          const id = ancora.dado(d.chave);
          return (
            <div key={d.chave} id={id} className={cn("space-y-1 p-3", classeAncora(id, destaque))} data-testid={`guia-dado-${d.chave}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{d.rotulo}</span>
                {d.escopo && <Badge variant="outline">{d.escopo}</Badge>}
              </div>
              <p className="text-sm text-muted-foreground">
                {d.documentos.length > 0 ? (
                  <>
                    Vem de:{" "}
                    {d.documentos.map((t, i) => (
                      <span key={t}>
                        {i > 0 && ", "}
                        <LinkDocumento guia={guia} tipo={t} />
                      </span>
                    ))}
                  </>
                ) : (
                  "Preenchido à mão."
                )}
              </p>
              {d.dica && <p className="text-xs text-muted-foreground">{d.dica}</p>}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function Documentos({ guia, destaque }: { guia: Guia; destaque: string | null }) {
  if (guia.documentos.length === 0) return <Vazio>Nenhum documento cadastrado.</Vazio>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="guia-documentos">
      {guia.documentos.map((d) => {
        const id = ancora.documento(d.tipo_documento);
        return (
          <Card key={d.tipo_documento} id={id} className={classeAncora(id, destaque)} data-testid={`guia-documento-${d.tipo_documento}`}>
            <CardContent className="space-y-2 p-4">
              <p className="font-semibold">{d.rotulo}</p>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Dados lidos</p>
                {d.campos.length > 0 ? (
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {d.campos.map((c) => (
                      <li key={c.campo}>
                        <Badge variant="secondary" className="font-normal">
                          {c.rotulo}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm italic text-muted-foreground">Nenhum campo lido automaticamente.</p>
                )}
              </div>
              {d.usos.length > 0 && (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Usado em</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
                    {d.usos.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                </div>
              )}
              {d.observacao && <p className="text-xs text-muted-foreground">{d.observacao}</p>}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function Certidoes({ guia, destaque }: { guia: Guia; destaque: string | null }) {
  if (guia.certidoes.length === 0) return <Vazio>Nenhuma certidão cadastrada.</Vazio>;
  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm" data-testid="guia-certidoes">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="p-2 font-medium">Linha</th>
              <th className="p-2 font-medium">Certidão</th>
              <th className="p-2 font-medium">Fonte</th>
              <th className="p-2 font-medium">Requisitos</th>
              <th className="p-2 font-medium">Credencial</th>
            </tr>
          </thead>
          <tbody>
            {guia.certidoes.map((c) => {
              const id = ancora.certidao(c.tipo);
              const requisitos = requisitosCertidao(c).filter((r) => r.startsWith("Precisa de"));
              return (
                <tr key={c.tipo} id={id} className={cn("border-b align-top last:border-b-0", classeAncora(id, destaque))} data-testid={`guia-certidao-${c.tipo}`}>
                  <td className="p-2 text-muted-foreground">{c.linha}</td>
                  <td className="p-2">
                    <span className="font-medium">{c.rotulo}</span>
                    {c.observacao && <p className="text-xs text-muted-foreground">{c.observacao}</p>}
                  </td>
                  <td className="p-2">{ROTULO_FONTE_CERTIDAO[c.fonte] ?? c.fonte}</td>
                  <td className="p-2">
                    {requisitos.length > 0 ? (
                      <ul className="space-y-0.5">
                        {requisitos.map((r) => (
                          <li key={r}>{r.replace(/^Precisa de: /, "")}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="p-2">
                    {c.credencial === "govbr" ? (
                      <span className="inline-flex items-center gap-1">
                        <KeyRound className="h-3.5 w-3.5 text-amber-600" aria-hidden="true" />
                        Login GOV.BR do escritório
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function BuscaPorDado({ guia, destaque }: { guia: Guia; destaque: string | null }) {
  const [termo, setTermo] = useState("");
  const resultados = useMemo(() => buscarCampos(guia, termo), [guia, termo]);
  return (
    <div className="space-y-3">
      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          type="search"
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          placeholder="Ex.: data de nascimento"
          aria-label="Buscar por dado"
          className="pl-8"
          data-testid="guia-busca-input"
        />
      </div>
      {resultados.length === 0 ? (
        <Vazio>
          {guia.campos.length === 0 ? "Nenhum dado indexado." : `Nenhum dado encontrado para "${termo.trim()}".`}
        </Vazio>
      ) : (
        <Card>
          <CardContent className="divide-y p-0" data-testid="guia-busca-resultados">
            {resultados.map((c) => {
              const id = ancora.campo(c.campo);
              return (
                <div key={c.campo} id={id} className={cn("flex flex-col gap-1 p-3 sm:flex-row sm:items-baseline sm:gap-3", classeAncora(id, destaque))} data-testid={`guia-campo-${c.campo}`}>
                  <span className="font-medium sm:w-56 sm:shrink-0">{c.rotulo}</span>
                  <span className="text-sm text-muted-foreground">
                    {c.documentos.length > 0
                      ? c.documentos.map((t, i) => (
                          <span key={t}>
                            {i > 0 && ", "}
                            <LinkDocumento guia={guia} tipo={t} />
                          </span>
                        ))
                      : "Nenhum documento fornece este dado."}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function GuiaDocumentos() {
  const q = useGuiaDocumentos();
  const destaque = useAncoraDestacada(!!q.data);

  return (
    <div className="container max-w-5xl space-y-8 py-6">
      <header className="space-y-3">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Guia de documentos</h1>
          {q.isRefreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="guia-atualizando" />}
        </div>
        <p className="text-sm text-muted-foreground">
          O que cada documento informa, o que cada certidão exige e o que cada etapa do lead pede — tudo gerado a
          partir das regras do sistema.
        </p>
        <nav aria-label="Seções do guia" className="flex flex-wrap gap-1.5">
          {SECOES_GUIA.map((s) => (
            <Link key={s.id} to={`#${s.id}`} className="rounded-full border px-3 py-1 text-xs hover:bg-muted">
              {s.titulo}
            </Link>
          ))}
        </nav>
      </header>

      {q.showSkeleton ? (
        <div className="space-y-3" data-testid="guia-carregando">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : !q.data ? (
        <QueryErrorState query={q} title="Não foi possível carregar o guia de documentos" data-testid="guia-erro" />
      ) : (
        <>
          <Secao id="fluxo-do-lead" titulo="Fluxo do lead" descricao="As etapas, em ordem, e o que cada uma exige.">
            <FluxoDoLead guia={q.data} destaque={destaque} />
          </Secao>
          <Secao id="dados-obrigatorios" titulo="Dados obrigatórios" descricao="O que todo cliente precisa ter, e de onde vem.">
            <DadosObrigatorios guia={q.data} destaque={destaque} />
          </Secao>
          <Secao id="documentos" titulo="Documentos" descricao="O que é lido de cada documento e onde é usado.">
            <Documentos guia={q.data} destaque={destaque} />
          </Secao>
          <Secao id="certidoes" titulo="Certidões" descricao="Fonte, requisitos e credencial de cada certidão.">
            <Certidoes guia={q.data} destaque={destaque} />
          </Secao>
          <Secao id="busca-por-dado" titulo="Busca por dado" descricao="Digite um dado para ver quais documentos o fornecem.">
            <BuscaPorDado guia={q.data} destaque={destaque} />
          </Secao>
        </>
      )}
    </div>
  );
}
