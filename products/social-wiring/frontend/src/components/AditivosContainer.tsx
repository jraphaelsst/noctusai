/**
 * `<AditivosContainer/>` — data for a signed contract's "Aditivos" block
 * (`card/aditivos/AditivosSection`), and `<AditivoGeracaoContainer/>` — data
 * for one aditivo's "Gerar aditivo" step. Same split as
 * `ContratosContainer` / `GeradorContratoContainer`: `card/**` stays
 * presentational; queries, mutations and the request-lifecycle state (a
 * save's refusal, a generation's 400 details / 201 avisos) live here.
 *
 * Favorecidos (the parcela payee picker) come from `useNegociacaoEstruturada`
 * — the SAME query the Negociação tab runs, so no second fetch path; it is
 * gated on the block being open, like the aditivos list itself.
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AditivoGeracaoSection } from "@/components/card/aditivos/AditivoGeracaoSection";
import { AditivosSection } from "@/components/card/aditivos/AditivosSection";
import type { GeracaoDestino } from "@/components/card/GeradorContratoSection";
import {
  aguardandoRevisaoJuridica,
  ContratoGeracaoError,
} from "@/hooks/useContratos";
import {
  useAditivoGeracao,
  useAditivoMutations,
  useAditivos,
  rotuloAditivo,
  type AditivoOut,
} from "@/hooks/useContratoAditivos";
import { useNegociacaoEstruturada } from "@/hooks/useNegociacaoEstruturada";
import { mensagemErroServidor, toastServerError } from "@/lib/erroServidor";

export interface AditivosContainerProps {
  clienteId: string;
  contratoId: string;
  /** Whether the contract card's "Aditivos" collapsible is open — the lazy
   *  gate for every fetch below. */
  aberto: boolean;
  podeAprovarRevisao: boolean;
  /** The card dialog's "Resolver" jump — forwarded to each readiness list. */
  onIrPara?: (destino: GeracaoDestino) => void;
}

export function AditivosContainer({
  clienteId,
  contratoId,
  aberto,
  podeAprovarRevisao,
  onIrPara,
}: AditivosContainerProps) {
  const query = useAditivos(clienteId, contratoId, aberto);
  const negociacao = useNegociacaoEstruturada(aberto ? clienteId : null);
  const { criar, atualizar, getUrl, aprovarRevisaoJuridica } = useAditivoMutations(
    clienteId,
    contratoId,
  );
  const [erroSalvar, setErroSalvar] = useState<{ aditivoId: string; mensagem: string } | null>(null);

  // 🔴 Two signals off `data`, never `isLoading` (lying-loading-state).
  const showSkeleton = query.isPending && !query.data && aberto;
  const isRefreshing = query.isFetching && !!query.data;

  async function abrirUrl(
    aditivoId: string,
    versaoId: string,
    intent: "view" | "download",
    formato?: "pdf" | "docx",
    impressao?: boolean,
  ) {
    try {
      // 🔴 Only from an explicit click — never pre-fetched.
      const res = await getUrl.mutateAsync({ aditivoId, versaoId, intent, formato, impressao });
      if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      toastServerError(
        err,
        intent === "view" ? "Não foi possível abrir o aditivo." : "Não foi possível baixar o aditivo.",
      );
    }
  }

  return (
    <AditivosSection
      aditivos={query.data}
      showSkeleton={showSkeleton}
      isRefreshing={isRefreshing}
      isError={query.isError}
      onRetry={() => query.refetch()}
      onCriar={(estilo) =>
        criar.mutate(
          { estilo },
          {
            onSuccess: (novo) =>
              toast.success(`${rotuloAditivo(novo.ordinal)} criado — preencha as alterações.`),
            onError: (err) => toastServerError(err, "Não foi possível criar o aditivo."),
          },
        )
      }
      criando={criar.isPending}
      favorecidos={negociacao.data?.favorecidos ?? []}
      onSalvar={(aditivoId, patch) => {
        setErroSalvar(null);
        atualizar.mutate(
          { aditivoId, patch },
          {
            onSuccess: () => toast.success("Aditivo salvo."),
            onError: (err) =>
              // Shown ON the editor (it stays dirty) — a toast alone could be
              // missed while the draft still reads as unsaved.
              setErroSalvar({
                aditivoId,
                mensagem: mensagemErroServidor(err, "Não foi possível salvar o aditivo."),
              }),
          },
        );
      }}
      salvandoAditivoId={
        atualizar.isPending && atualizar.variables?.patch.status === undefined
          ? (atualizar.variables?.aditivoId ?? null)
          : null
      }
      erroSalvar={erroSalvar}
      onPatchStatus={(aditivoId, status) =>
        atualizar.mutate(
          { aditivoId, patch: { status } },
          { onError: (err) => toastServerError(err, "Não foi possível atualizar o status do aditivo.") },
        )
      }
      renderGeracao={(aditivo, geracaoAberta, temAlteracoesNaoSalvas) => (
        <AditivoGeracaoContainer
          clienteId={clienteId}
          contratoId={contratoId}
          aditivo={aditivo}
          aberto={geracaoAberta}
          temAlteracoesNaoSalvas={temAlteracoesNaoSalvas}
          onIrPara={onIrPara}
        />
      )}
      onOpenVersao={(aditivoId, versaoId, formato) => void abrirUrl(aditivoId, versaoId, "view", formato)}
      onDownloadVersao={(aditivoId, versaoId, formato, opcoes) =>
        void abrirUrl(aditivoId, versaoId, "download", formato, opcoes?.impressao)
      }
      baixandoDocxVersaoId={
        getUrl.isPending && getUrl.variables?.formato === "docx"
          ? (getUrl.variables?.versaoId ?? null)
          : null
      }
      podeAprovarRevisao={podeAprovarRevisao}
      onAprovarRevisao={(aditivoId, versaoId) =>
        aprovarRevisaoJuridica.mutate(
          { aditivoId, versaoId },
          {
            onSuccess: () => toast.success("Revisão jurídica do aditivo aprovada."),
            onError: (err) => toastServerError(err, "Não foi possível aprovar a revisão jurídica."),
          },
        )
      }
      aprovandoAditivoId={
        aprovarRevisaoJuridica.isPending ? (aprovarRevisaoJuridica.variables?.aditivoId ?? null) : null
      }
    />
  );
}

export function AditivoGeracaoContainer({
  clienteId,
  contratoId,
  aditivo,
  aberto,
  temAlteracoesNaoSalvas,
  onIrPara,
}: {
  clienteId: string;
  contratoId: string;
  aditivo: AditivoOut;
  aberto: boolean;
  temAlteracoesNaoSalvas: boolean;
  onIrPara?: (destino: GeracaoDestino) => void;
}) {
  const query = useAditivoGeracao(clienteId, contratoId, aditivo.id, aberto);
  const { gerar } = useAditivoMutations(clienteId, contratoId);
  const [assinaturaData, setAssinaturaData] = useState("");
  const [erroGeracao, setErroGeracao] = useState<ContratoGeracaoError | null>(null);
  const [avisosGerados, setAvisosGerados] = useState<string[] | null>(null);

  // The date input follows the server's "date gerar will use" until the
  // operator types one — then it is theirs.
  const dataTocadaRef = useRef(false);
  const dataServidor = query.data?.assinatura_data ?? "";
  useEffect(() => {
    if (!dataTocadaRef.current) setAssinaturaData(dataServidor);
  }, [dataServidor]);

  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  function handleGerar() {
    setErroGeracao(null);
    setAvisosGerados(null);
    gerar.mutate(
      { aditivoId: aditivo.id, assinaturaData: assinaturaData || undefined },
      {
        onSuccess: (result) => {
          setAvisosGerados(result.avisos.map((a) => a.mensagem));
          toast.success(
            aguardandoRevisaoJuridica(result.versao)
              ? "Nova versão do aditivo gerada — aguardando revisão jurídica."
              : "Nova versão do aditivo gerada.",
          );
        },
        onError: (err) => {
          if (err instanceof ContratoGeracaoError) {
            setErroGeracao(err);
            // The data behind the refusal may have moved since the check.
            void query.refetch();
            return;
          }
          toastServerError(err, "Não foi possível gerar o aditivo.");
        },
      },
    );
  }

  return (
    <AditivoGeracaoSection
      aditivoId={aditivo.id}
      geracao={query.data}
      showSkeleton={showSkeleton}
      isRefreshing={isRefreshing}
      isError={query.isError && !query.data}
      onRetry={() => query.refetch()}
      assinaturaData={assinaturaData}
      onAssinaturaDataChange={(v) => {
        dataTocadaRef.current = true;
        setAssinaturaData(v);
      }}
      gerando={gerar.isPending}
      onGerar={handleGerar}
      erroGeracao={erroGeracao}
      avisosGerados={avisosGerados}
      temAlteracoesNaoSalvas={temAlteracoesNaoSalvas}
      onIrPara={onIrPara}
    />
  );
}

export default AditivosContainer;
