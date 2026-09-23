/**
 * `<ContratosContainer/>` — data for the card's Contratos subpage.
 *
 * Same split as `FinanciamentoContainer`/`NegociacaoContainer`: the dialog
 * stays presentational and this owns the query + the mutations that do not
 * need their own modal (status change, new version, deletes, open/download).
 *
 * The CREATE dialog is deliberately NOT owned here — `NovoContratoDialog`
 * renders as a sibling of the card in `ClienteDetailModal` (see its header
 * comment), so this container only receives `onNovoContrato` to flip that
 * dialog's `open` boolean.
 *
 * 🔴 `renderMatriculaAtos` narrows the picker to THIS deal's imóvel: the
 * código comes from `atendimento_negociacao.imovel_codigo` (the same
 * `useNegociacao` query the Negociação tab already runs, so no extra
 * request). The backend refuses a selection from another imóvel's matrícula
 * regardless — this only keeps the operator from being offered one. While the
 * deal has no imóvel yet the picker lists every transcribed matrícula.
 *
 * 🔴 ASSINATURA DIGITAL (signature-integration-CONTRACT §4) — same reuse
 * discipline as `renderMatriculaAtos`: `useCompradores(clienteId)` /
 * `useCompradores(clienteId, "vendedor")` are the SAME hook the Compradores/
 * Vendedores tabs already call (`ClienteDetailModal`), and `useTestemunhas`
 * is the SAME hook the settings page uses — no second fetch path is added
 * for the "Enviar para assinatura" dialog's prefill. `useAssinaturas` is
 * scoped to only the contracts that have ever had a `gerado` version (an
 * upload-only contract can never have gone through this flow, so it never
 * fires a GET that can only 404). The dialog itself
 * (`EnviarAssinaturaDialog`) is mounted here as a SIBLING of `ContratosPanel`
 * — not a child render prop — because it needs no per-card layout, only the
 * one open target (`envioAlvo`) this container already owns.
 */
import { useState } from "react";
import { toast } from "sonner";

import { useAuthStore } from "@noctusai/seed/infra";
import { ApiError, resolveSSOContext } from "@noctusai/lib";

import { GeradorContratoContainer } from "@/components/GeradorContratoContainer";
import { MatriculaAtosContainer } from "@/components/MatriculaAtosContainer";
import { ProvenienciaContainer } from "@/components/ProvenienciaContainer";
import { EnviarAssinaturaDialog } from "@/components/card/EnviarAssinaturaDialog";
import ContratosPanel from "@/components/card/ContratosPanel";
import { useCompradores } from "@/hooks/useCardHub";
import {
  AssinaturaError,
  useAssinaturas,
  useContratoMutations,
  useContratos,
} from "@/hooks/useContratos";
import { useNegociacao } from "@/hooks/useNegociacao";
import { useTestemunhas } from "@/hooks/useTestemunhas";

function toastServerError(err: unknown, fallback: string) {
  // A typed server refusal (`{error: {code, message}}` — e.g. migration
  // 157's 409 CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO) carries its own
  // pt-BR sentence; `ApiError.message` would prefix it with the status.
  const envelope =
    err instanceof ApiError ? (err.body as { error?: { message?: string } } | undefined) : undefined;
  const message =
    envelope?.error?.message || (err instanceof Error && err.message ? err.message : fallback);
  toast.error(message);
}

export function ContratosContainer({
  clienteId,
  onNovoContrato,
}: {
  clienteId: string;
  onNovoContrato: () => void;
}) {
  const query = useContratos(clienteId);
  const mutations = useContratoMutations(clienteId);
  // Migration 151 (owner directive 2026-09-22). A UI convenience ONLY —
  // same posture `ConflitosPendentesPanel`'s own `isAdmin` already takes:
  // the server's `PUT .../processo-legado` reads the TRUSTED `noctus_users`
  // row and 403s a spoofed claim regardless of what this renders.
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin =
    ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";
  // The deal's imóvel — narrows the matrícula picker (see header note).
  const negociacao = useNegociacao(clienteId);
  const imovelCodigo = negociacao.data?.imovel_codigo ?? null;
  const [contratoIniciadoId, setContratoIniciadoId] = useState<string | null>(null);

  // ─── Assinatura digital (§4) — same reuse discipline as `imovelCodigo`
  // above: these are the SAME hooks the Compradores/Vendedores tabs and the
  // settings page already call (see header note), not a second fetch path.
  const compradores = useCompradores(clienteId);
  const vendedores = useCompradores(clienteId, "vendedor");
  const testemunhas = useTestemunhas();
  const contratoIdsElegiveis = (query.data ?? [])
    .filter((c) => c.origem === "gerado" || c.versoes.some((v) => v.origem === "gerado"))
    .map((c) => c.id);
  const assinaturas = useAssinaturas(clienteId, contratoIdsElegiveis);
  const [envioAlvo, setEnvioAlvo] = useState<{ contratoId: string; versaoId: string } | null>(
    null,
  );
  const [erroEnvio, setErroEnvio] = useState<AssinaturaError | null>(null);

  function fecharEnvioDialog(open: boolean) {
    if (!open) {
      setEnvioAlvo(null);
      setErroEnvio(null);
    }
  }

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // an empty/error branch keyed off it would lie over data that is still
  // good to look at.
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  return (
    <>
      <ContratosPanel
        contratos={query.data}
        showSkeleton={showSkeleton}
        isRefreshing={isRefreshing}
        isError={query.isError}
        errorMessage={query.error instanceof Error ? query.error.message : null}
        onRetry={() => query.refetch()}
        onNovoContrato={onNovoContrato}
        onGerarContrato={() =>
          mutations.iniciar.mutate(undefined, {
            onSuccess: (res) => {
              setContratoIniciadoId(res.contrato.id);
              toast.success(
                res.geracao.pronto
                  ? "Contrato criado — pronto para gerar."
                  : "Contrato criado — confira os dados que faltam para gerar.",
              );
            },
            onError: (err) => toastServerError(err, "Não foi possível iniciar o contrato."),
          })
        }
        iniciandoGeracao={mutations.iniciar.isPending}
        contratoIniciadoId={contratoIniciadoId}
        addingVersaoContratoId={
          mutations.addVersao.isPending
            ? (mutations.addVersao.variables?.contratoId ?? null)
            : null
        }
        patchingContratoId={
          mutations.patch.isPending ? (mutations.patch.variables?.contratoId ?? null) : null
        }
        deletingVersaoId={
          mutations.deleteVersao.isPending
            ? (mutations.deleteVersao.variables?.versaoId ?? null)
            : null
        }
        deletingContratoId={
          mutations.deleteContrato.isPending
            ? (mutations.deleteContrato.variables?.contratoId ?? null)
            : null
        }
        // 🔴 Same `getUrl` mutation as Abrir/Baixar — narrowed to `formato
        // === "docx"` so only the ".docx" button spins, not the PDF ones.
        baixandoDocxVersaoId={
          mutations.getUrl.isPending && mutations.getUrl.variables?.formato === "docx"
            ? (mutations.getUrl.variables?.versaoId ?? null)
            : null
        }
        onAddVersao={(contratoId, file) =>
          mutations.addVersao.mutate(
            { contratoId, file },
            { onError: (err) => toastServerError(err, "Não foi possível enviar a nova versão.") },
          )
        }
        onPatchStatus={(contratoId, status) =>
          mutations.patch.mutate(
            { contratoId, patch: { status } },
            { onError: (err) => toastServerError(err, "Não foi possível atualizar o status.") },
          )
        }
        onPatchPrazos={(contratoId, patch) =>
          mutations.patch.mutate(
            { contratoId, patch },
            {
              onError: (err) =>
                toastServerError(err, "Não foi possível salvar os prazos do contrato."),
            },
          )
        }
        onDeleteVersao={(contratoId, versaoId, motivo) =>
          mutations.deleteVersao.mutate(
            { contratoId, versaoId, motivo },
            { onError: (err) => toastServerError(err, "Não foi possível remover a versão.") },
          )
        }
        onDeleteContrato={(contratoId, motivo) =>
          mutations.deleteContrato.mutate(
            { contratoId, motivo },
            { onError: (err) => toastServerError(err, "Não foi possível remover o contrato.") },
          )
        }
        onOpen={async (contratoId, versaoId, formato) => {
          try {
            // 🔴 Fired only from an explicit click, same discipline as the
            // financiamento document URL — never pre-fetched or refreshed.
            const res = await mutations.getUrl.mutateAsync({
              contratoId,
              versaoId,
              intent: "view",
              formato,
            });
            if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
          } catch (err) {
            toastServerError(err, "Não foi possível abrir o contrato.");
          }
        }}
        onDownload={async (contratoId, versaoId, formato) => {
          try {
            const res = await mutations.getUrl.mutateAsync({
              contratoId,
              versaoId,
              intent: "download",
              formato,
            });
            if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
          } catch (err) {
            toastServerError(err, "Não foi possível baixar o contrato.");
          }
        }}
        renderMatriculaAtos={(contratoId) => (
          // `clienteId` is what lets the picker offer one section per PERMUTA
          // ativo of this deal (migration 115): the ativos come from the deal's
          // negociação estruturada, which is keyed by cliente, not by contract.
          <MatriculaAtosContainer
            contratoId={contratoId}
            codigo={imovelCodigo}
            clienteId={clienteId}
          />
        )}
        renderGeradorContrato={(contratoId, aberto) => (
          <GeradorContratoContainer clienteId={clienteId} contratoId={contratoId} aberto={aberto} />
        )}
        renderProveniencia={(contratoId, aberto) => (
          <ProvenienciaContainer clienteId={clienteId} contratoId={contratoId} aberto={aberto} />
        )}
        assinaturas={assinaturas}
        onAbrirEnvioAssinatura={(contratoId, versaoId) => {
          setErroEnvio(null);
          setEnvioAlvo({ contratoId, versaoId });
        }}
        onCancelarAssinatura={(contratoId, motivo) =>
          mutations.cancelarAssinatura.mutate(
            { contratoId, motivo },
            { onError: (err) => toastServerError(err, "Não foi possível cancelar o envio.") },
          )
        }
        cancelandoAssinaturaContratoId={
          mutations.cancelarAssinatura.isPending
            ? (mutations.cancelarAssinatura.variables?.contratoId ?? null)
            : null
        }
        isAdmin={isAdmin}
        onSetProcessoLegado={(contratoId, ativo, motivo) =>
          mutations.processoLegado.mutate(
            { contratoId, ativo, motivo },
            {
              onError: (err) =>
                toastServerError(
                  err,
                  "Não foi possível atualizar o processo anterior à plataforma.",
                ),
            },
          )
        }
        settingProcessoLegadoContratoId={
          mutations.processoLegado.isPending
            ? (mutations.processoLegado.variables?.contratoId ?? null)
            : null
        }
        // Migration 157 — the Digital/Física signing gate.
        onPatchModalidade={(contratoId, modalidade) =>
          mutations.patch.mutate(
            { contratoId, patch: { modalidade_assinatura: modalidade } },
            {
              onSuccess: () =>
                toast.success(
                  modalidade === "fisica"
                    ? "Assinatura física — gere uma nova versão para imprimir."
                    : "Assinatura digital.",
                ),
              onError: (err) =>
                toastServerError(err, "Não foi possível mudar a modalidade de assinatura."),
            },
          )
        }
        onMarcarAssinadoFisico={(contratoId, file) =>
          mutations.marcarAssinadoFisico.mutate(
            { contratoId, file },
            {
              onSuccess: () =>
                toast.success(file ? "Contrato assinado anexado." : "Contrato marcado como assinado."),
              onError: (err) =>
                toastServerError(err, "Não foi possível marcar o contrato como assinado."),
            },
          )
        }
        marcandoAssinadoContratoId={
          mutations.marcarAssinadoFisico.isPending
            ? (mutations.marcarAssinadoFisico.variables?.contratoId ?? null)
            : null
        }
      />
      <EnviarAssinaturaDialog
        open={!!envioAlvo}
        onOpenChange={fecharEnvioDialog}
        compradores={compradores.data?.items ?? []}
        vendedores={vendedores.data?.items ?? []}
        testemunhas={testemunhas.data?.items ?? []}
        sending={mutations.enviarParaAssinatura.isPending}
        erro={erroEnvio}
        onEnviar={({ signatarios, mensagem }) => {
          if (!envioAlvo) return;
          mutations.enviarParaAssinatura.mutate(
            {
              contratoId: envioAlvo.contratoId,
              versaoId: envioAlvo.versaoId,
              signatarios,
              mensagem,
            },
            {
              onSuccess: () => {
                setEnvioAlvo(null);
                setErroEnvio(null);
                toast.success("Enviado para assinatura.");
              },
              onError: (err) => {
                // 🔴 Every §3.1 error row is handled here — the dialog stays
                // open and renders `err.message`/`err.details` (422's
                // `faltando`, 502's `provedor_mensagem`) rather than a toast
                // that would hide the refusal the moment it appears.
                if (err instanceof AssinaturaError) {
                  setErroEnvio(err);
                  return;
                }
                toastServerError(err, "Não foi possível enviar para assinatura.");
              },
            },
          );
        }}
      />
    </>
  );
}
