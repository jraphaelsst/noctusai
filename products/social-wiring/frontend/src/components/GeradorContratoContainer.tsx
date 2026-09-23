/**
 * `<GeradorContratoContainer/>` — data for `<GeradorContratoSection/>`.
 *
 * Same split as `MatriculaAtosContainer`: everything under `card/**` is
 * presentational (S3 discipline) and this file owns the readiness query
 * (`useContratoGeracao`) and the generate mutation (`useContratoMutations`'s
 * `gerar`). The date draft, and the transient "what did the last attempt
 * return" state (a 400's `details`, a 201's `avisos`) live here too — they
 * are request lifecycle, not layout.
 *
 * 🔴 OWNER DECISION D2 — "Gerar versão" first asks the backend which
 * machine-extracted values are still unvalidated (`useValidacaoExtracao`).
 * Any (or an open extraction conflict) → `<ValidacaoExtracaoDialog/>` opens (✓/✗ per value, accept/reject
 * all, inline manual input for a rejected required value); none → the
 * existing generate call runs. A 409 `EXTRACAO_PENDENTE_VALIDACAO` from
 * `gerar` (the backend gate — a value extracted between the check and the
 * click) reopens the dialog rather than surfacing as a bare error.
 */
import { useState } from "react";
import { toast } from "sonner";

import GeradorContratoSection, { type GeracaoDestino } from "@/components/card/GeradorContratoSection";
import ValidacaoExtracaoDialog from "@/components/card/ValidacaoExtracaoDialog";
import {
  ContratoGeracaoError,
  useContratoGeracao,
  useContratoMutations,
} from "@/hooks/useContratos";
import {
  CODIGO_PENDENTE_VALIDACAO,
  CODIGO_VALIDACAO_DESATUALIZADA,
  codigoDoErro,
  useValidacaoExtracao,
  useValidacaoExtracaoMutations,
  type DecisaoInput,
  type PendenteValidacao,
} from "@/hooks/useValidacaoExtracao";

export interface GeradorContratoContainerProps {
  clienteId: string;
  contratoId: string;
  /** Whether the "Gerar contrato" collapsible is open — the lazy gate the F5
   *  brief asks for. See `useContratoGeracao`'s header note. */
  aberto: boolean;
  /** Card-scoped "Resolver" — switches the card subpage and lands on the
   *  falta's control. Handed down from the card dialog; absent elsewhere. */
  onIrPara?: (destino: GeracaoDestino) => void;
}

/**
 * Today in São Paulo as `YYYY-MM-DD` — the same default the backend applies
 * when `assinatura_data` is omitted. `toISOString()` is UTC, which after 21h
 * local time is already tomorrow and would silently date the contract a day
 * late.
 */
function hoje(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function GeradorContratoContainer({
  clienteId,
  contratoId,
  aberto,
  onIrPara,
}: GeradorContratoContainerProps) {
  const query = useContratoGeracao(clienteId, contratoId, aberto);
  const { gerar } = useContratoMutations(clienteId);

  const [assinaturaData, setAssinaturaData] = useState(hoje);
  const [erroGeracao, setErroGeracao] = useState<ContratoGeracaoError | null>(null);
  const [avisosGerados, setAvisosGerados] = useState<string[] | null>(null);

  const [validacaoAberta, setValidacaoAberta] = useState(false);
  /** REQUIRED values rejected in this dialog session — they left the pending
   *  list (the value is now empty), so a snapshot drives the inline input. */
  const [rejeitados, setRejeitados] = useState<PendenteValidacao[]>([]);
  const [salvandoChave, setSalvandoChave] = useState<string | null>(null);
  const validacao = useValidacaoExtracao(clienteId, contratoId, validacaoAberta);
  const { verificar, decidir, salvarManual } = useValidacaoExtracaoMutations(clienteId, contratoId);

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // an empty/error branch keyed off it would lie over data still good to
  // look at (`KB § PATTERNS/frontend/lying-loading-state.md`).
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const validacaoSkeleton = validacao.isPending && !validacao.data;
  const validacaoRefreshing = validacao.isFetching && !!validacao.data;

  function abrirValidacao() {
    setRejeitados([]);
    setValidacaoAberta(true);
  }

  function executarGerar() {
    gerar.mutate(
      { contratoId, assinaturaData: assinaturaData || undefined },
      {
        onSuccess: (result) => {
          setValidacaoAberta(false);
          setAvisosGerados(result.avisos.map((a) => a.mensagem));
          toast.success("Nova versão gerada.");
        },
        onError: (err) => {
          if (err instanceof ContratoGeracaoError && err.code === CODIGO_PENDENTE_VALIDACAO) {
            // The backend gate: something became pending after the check.
            void validacao.refetch();
            abrirValidacao();
            return;
          }
          if (
            err instanceof ContratoGeracaoError &&
            (err.code === "CONTRATO_INCOMPLETO" || err.code === "CONTRATO_LINT")
          ) {
            setValidacaoAberta(false);
            setErroGeracao(err);
            // The data behind the refusal may have changed since the readiness
            // check ran — show the current state next to the error.
            void query.refetch();
            return;
          }
          toast.error(err instanceof Error ? err.message : "Não foi possível gerar o contrato.");
        },
      },
    );
  }

  function handleGerar() {
    setErroGeracao(null);
    setAvisosGerados(null);
    verificar.mutate(undefined, {
      onSuccess: ({ pendentes, conflitos }) => {
        if (pendentes.length > 0 || conflitos.length > 0) {
          abrirValidacao();
          return;
        }
        executarGerar();
      },
      onError: () => {
        toast.error("Não foi possível verificar os dados extraídos. Tente novamente.");
      },
    });
  }

  function handleDecidir(decisoes: DecisaoInput[]) {
    const atuais = new Map((validacao.data?.pendentes ?? []).map((p) => [p.chave, p]));
    decidir.mutate(decisoes, {
      onSuccess: () => {
        const novos = decisoes
          .filter((d) => d.decisao === "rejeitado")
          .map((d) => atuais.get(d.chave))
          .filter((p): p is PendenteValidacao => !!p && p.obrigatorio);
        if (novos.length > 0) {
          setRejeitados((prev) => [
            ...prev.filter((p) => !novos.some((n) => n.chave === p.chave)),
            ...novos,
          ]);
        }
        // A reject empties a value — the readiness report must reflect it.
        void query.refetch();
      },
      onError: (err) => {
        toast.error(
          codigoDoErro(err) === CODIGO_VALIDACAO_DESATUALIZADA
            ? "A lista mudou desde que foi aberta — confira os itens atualizados."
            : "Não foi possível registrar a decisão.",
        );
      },
    });
  }

  function handleSalvarManual(item: PendenteValidacao, valor: string) {
    if (!item.edicao) return;
    setSalvandoChave(item.chave);
    salvarManual.mutate(
      { edicao: item.edicao, valor },
      {
        onSuccess: () => {
          setRejeitados((prev) => prev.filter((p) => p.chave !== item.chave));
          toast.success(`${item.rotulo} salvo.`);
          void query.refetch();
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Não foi possível salvar o valor.");
        },
        onSettled: () => setSalvandoChave(null),
      },
    );
  }

  return (
    <>
      <GeradorContratoSection
        status={query.data}
        showSkeleton={showSkeleton}
        isRefreshing={isRefreshing}
        isError={query.isError && !query.data}
        onRetry={() => query.refetch()}
        assinaturaData={assinaturaData}
        onAssinaturaDataChange={setAssinaturaData}
        gerando={gerar.isPending || verificar.isPending}
        onGerar={handleGerar}
        erroGeracao={erroGeracao}
        avisosGerados={avisosGerados}
        onIrPara={onIrPara}
      />
      <ValidacaoExtracaoDialog
        open={validacaoAberta}
        onOpenChange={setValidacaoAberta}
        pendentes={validacao.data?.pendentes}
        conflitos={validacao.data?.conflitos ?? []}
        showSkeleton={validacaoSkeleton}
        isRefreshing={validacaoRefreshing}
        isError={validacao.isError && !validacao.data}
        onRetry={() => validacao.refetch()}
        decidindo={decidir.isPending}
        onDecidir={handleDecidir}
        rejeitados={rejeitados}
        salvandoChave={salvandoChave}
        onSalvarManual={handleSalvarManual}
        gerando={gerar.isPending}
        onProsseguir={executarGerar}
      />
    </>
  );
}
