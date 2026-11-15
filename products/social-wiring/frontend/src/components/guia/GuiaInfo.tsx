/**
 * The Social Wiring "i" popovers — thin wrappers over the seed `InfoPopover`
 * organ that look one entry up in `GET /api/guia-documentos`:
 *
 *   - `DocumentoInfo tipo=…`        — "Dados lidos deste documento" + "Usado em"
 *   - `CertidaoInfo tipo=…`         — the requirement sentences (CPF + data de
 *                                     nascimento, GOV.BR login, manual)
 *   - `DadoObrigatorioInfo chave=…` — which documents supply a checklist item
 *
 * Each ends with "Ver no guia" → `/guia-documentos#<anchor>`.
 *
 * The data hook lives in the popover BODY, which the seed organ mounts only
 * while open — so the card rows that carry these icons stay presentational
 * (no fetch, no query provider needed) until someone actually opens one, and
 * every "i" shares the page's single cached query (1h staleTime).
 *
 * Every state is drawn: a skeleton while the guide loads, the query's own
 * refusal (`QueryErrorState`, compact) — never an empty bubble — and an
 * explicit "not in the guide" line for a tipo the catalog does not know.
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { InfoPopover, InfoSecoes, QueryErrorState } from "@noctusai/lib/components";

import { Skeleton } from "@/components/ui/skeleton";
import { useGuiaDocumentos } from "@/hooks/useGuiaDocumentos";
import {
  ancora,
  certidaoPorTipo,
  dadoObrigatorioPorChave,
  documentoPorTipo,
  linkGuia,
  requisitosCertidao,
  rotuloDocumento,
} from "@/lib/guiaDocumentos";
import type { GuiaDocumentos } from "@/types/guiaDocumentos";

function VerNoGuia({ id }: { id: string }) {
  return (
    <Link to={linkGuia(id)} className="font-medium text-primary hover:underline" data-testid="guia-info-link">
      Ver no guia
    </Link>
  );
}

/** Loading / refusal / not-found frame shared by the three bodies. */
function CorpoGuia({
  render,
  ancoraId,
}: {
  render: (guia: GuiaDocumentos) => ReactNode | null;
  ancoraId: string;
}) {
  const q = useGuiaDocumentos();
  if (q.showSkeleton) {
    return (
      <div className="space-y-2" data-testid="guia-info-carregando">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
      </div>
    );
  }
  if (!q.data) {
    return <QueryErrorState query={q} variant="inline" title="Não foi possível carregar o guia" data-testid="guia-info-erro" />;
  }
  const corpo = render(q.data);
  if (corpo === null) {
    return (
      <InfoSecoes
        secoes={[]}
        nota="Este item ainda não está descrito no guia de documentos."
        rodape={<VerNoGuia id={ancoraId} />}
        testId="guia-info-ausente"
      />
    );
  }
  return <>{corpo}</>;
}

function corpoDocumento(guia: GuiaDocumentos, tipo: string): ReactNode | null {
  const d = documentoPorTipo(guia, tipo);
  if (!d) return null;
  return (
    <InfoSecoes
      titulo={d.rotulo}
      secoes={[
        {
          titulo: "Dados lidos deste documento",
          itens: d.campos.map((c) => c.rotulo),
          vazio: "Nenhum campo é lido automaticamente.",
        },
        { titulo: "Usado em", itens: d.usos },
      ]}
      nota={d.observacao}
      rodape={<VerNoGuia id={ancora.documento(tipo)} />}
      testId="guia-info-documento"
    />
  );
}

function corpoCertidao(guia: GuiaDocumentos, tipo: string): ReactNode | null {
  const c = certidaoPorTipo(guia, tipo);
  if (!c) return null;
  return (
    <InfoSecoes
      titulo={`${c.linha} · ${c.rotulo}`}
      secoes={[{ titulo: "Requisitos", itens: requisitosCertidao(c), vazio: "Nenhum requisito além da parte." }]}
      nota={c.observacao}
      rodape={<VerNoGuia id={ancora.certidao(tipo)} />}
      testId="guia-info-certidao"
    />
  );
}

function corpoDadoObrigatorio(guia: GuiaDocumentos, chave: string): ReactNode | null {
  const d = dadoObrigatorioPorChave(guia, chave);
  if (!d) return null;
  return (
    <InfoSecoes
      titulo={d.rotulo}
      secoes={[
        {
          titulo: "Documentos que fornecem",
          itens: d.documentos.map((t) => rotuloDocumento(guia, t)),
          vazio: "Preenchido à mão — nenhum documento fornece este dado.",
        },
      ]}
      nota={[d.dica, d.escopo ? `Vale para: ${d.escopo}` : null].filter(Boolean).join(" · ") || null}
      rodape={<VerNoGuia id={ancora.dado(chave)} />}
      testId="guia-info-dado"
    />
  );
}

interface InfoBaseProps {
  /** Shown in the trigger's accessible name ("Sobre: RG"); the guide's own
   *  label is only known once the body loads. */
  rotulo?: string;
  className?: string;
}

export function DocumentoInfo({ tipo, rotulo, className }: InfoBaseProps & { tipo: string }) {
  return (
    <InfoPopover label={`Sobre: ${rotulo ?? tipo}`} testId={`documento-info-${tipo}`} className={className}>
      <CorpoGuia render={(g) => corpoDocumento(g, tipo)} ancoraId={ancora.documento(tipo)} />
    </InfoPopover>
  );
}

export function CertidaoInfo({ tipo, rotulo, className }: InfoBaseProps & { tipo: string }) {
  return (
    <InfoPopover label={`Sobre: ${rotulo ?? tipo}`} testId={`certidao-info-${tipo}`} className={className}>
      <CorpoGuia render={(g) => corpoCertidao(g, tipo)} ancoraId={ancora.certidao(tipo)} />
    </InfoPopover>
  );
}

export function DadoObrigatorioInfo({ chave, rotulo, className }: InfoBaseProps & { chave: string }) {
  return (
    <InfoPopover label={`Sobre: ${rotulo ?? chave}`} testId={`dado-info-${chave}`} className={className}>
      <CorpoGuia render={(g) => corpoDadoObrigatorio(g, chave)} ancoraId={ancora.dado(chave)} />
    </InfoPopover>
  );
}
