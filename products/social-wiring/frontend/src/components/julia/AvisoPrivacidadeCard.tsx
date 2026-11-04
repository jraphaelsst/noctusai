/**
 * Julia › Agente card (d): the org's public privacy notice (contract 11.2), READ-ONLY (owner 2026-11-04: Julia's content is
 * configured by NoctusAI). It shows the text and the public-page link; no inputs, no save. NoctusAI staff edit it through the
 * platform-admin-only `PUT /api/julia/agente/aviso`.
 */
import { AlertTriangle, ExternalLink } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useJuliaAviso, type JuliaAvisoAdmin } from "@/hooks/useJuliaAviso";
import { blocosParaTexto } from "@/lib/juliaAviso";

export const NOTA_AVISO_NOCTUS =
  "O aviso de privacidade da Julia é configurado pela equipe NoctusAI. Para alterar, fale com o suporte.";

function Linha({ rotulo, valor, testid }: { rotulo: string; valor: string | null | undefined; testid?: string }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{rotulo}</dt>
      <dd className="whitespace-pre-wrap text-sm" data-testid={testid}>
        {valor?.trim() ? valor : <span className="text-muted-foreground">Não definido</span>}
      </dd>
    </div>
  );
}

function AvisoLeitura({ aviso }: { aviso: JuliaAvisoAdmin }) {
  return (
    <div className="space-y-4">
      {aviso.incompleto && (
        <p role="alert" className="flex items-start gap-2 text-sm text-warning-foreground" data-testid="aviso-incompleto">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            O aviso ainda tem campos "a definir" (nome da empresa ou contato). A Julia não pode ser ligada até que a equipe
            NoctusAI o complete: fale com o suporte.
          </span>
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-2" data-testid="aviso-leitura">
        <Linha rotulo="Título" valor={aviso.titulo} testid="aviso-titulo" />
        <Linha rotulo="Empresa (controlador)" valor={aviso.empresa_nome} testid="aviso-empresa" />
        <Linha rotulo="E-mail de contato" valor={aviso.contato_email} />
        <Linha rotulo="WhatsApp de contato" valor={aviso.contato_whatsapp} />
      </dl>
      <dl>
        <Linha rotulo="Mensagem inicial" valor={aviso.mensagem_inicial} testid="aviso-mensagem" />
      </dl>
      <div className="space-y-3">
        {aviso.secoes.map((s, i) => (
          <div key={i} className="space-y-1 rounded-md border p-3" data-testid={`aviso-secao-${i}`}>
            <p className="text-sm font-medium">
              {s.n}. {s.title}
            </p>
            <p className="whitespace-pre-wrap text-sm">{blocosParaTexto(s.blocks)}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground" data-testid="aviso-nota-suporte">
        {NOTA_AVISO_NOCTUS}
      </p>
      <a
        href={`/privacidade/${aviso.slug}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm text-primary underline"
        data-testid="aviso-pagina-publica"
      >
        Ver página pública <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </div>
  );
}

// `isAdmin` is accepted so the page keeps its call shape; nobody edits here, whatever the role.
export function AvisoPrivacidadeCard(_props: { isAdmin?: boolean } = {}) {
  const q = useJuliaAviso();
  const showSkeleton = q.isPending && !q.data;

  return (
    <Card data-testid="aviso-card">
      <CardHeader>
        <CardTitle className="text-base">Aviso de privacidade</CardTitle>
        <CardDescription>
          Página pública enviada ao lead na primeira mensagem (LGPD). A empresa é o controlador dos dados.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {showSkeleton ? (
          <div className="h-40 animate-pulse rounded-md bg-muted" data-testid="aviso-skeleton" />
        ) : q.isError && !q.data ? (
          <p role="alert" className="text-sm text-destructive" data-testid="aviso-erro">
            Não foi possível carregar o aviso de privacidade.{" "}
            <button className="underline" onClick={() => q.refetch()}>
              Tentar de novo
            </button>
          </p>
        ) : q.data ? (
          <AvisoLeitura aviso={q.data} />
        ) : null}
      </CardContent>
    </Card>
  );
}
