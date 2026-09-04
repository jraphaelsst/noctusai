/**
 * ImovelDetalhes — one imóvel, full record.
 *
 * Route: /imoveis/:codigo. Reads the local mirror; a code that was never
 * synced 404s rather than silently falling back to a live Vista call, so the
 * page never disagrees with the catalog it was reached from.
 *
 * CONTRACT § 5 — the 13-section display, in order. Everything past the
 * header is a small presentational component under `components/imovel/`,
 * each deciding for itself whether it has ≥1 non-null field to show.
 *
 * Rendering decisions that encode measured wire facts:
 *   · Counts use formatCount so a genuine 0 (terreno) reads "0", while
 *     unknown reads "—".
 *   · ALL corretores are listed; 13.1% of imóveis have 2-3.
 *   · Every boolean is Sim/Não, never true/false, and null hides the field
 *     entirely (formatBool) — not a "—" placeholder, per CONTRACT § 7.
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Megaphone,
  Mail,
  Star,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import EditPlaceholderButton from "@/components/imovel/EditPlaceholderButton";
import ImovelAreasSection from "@/components/imovel/ImovelAreasSection";
import ImovelCartorioCard from "@/components/imovel/ImovelCartorioCard";
import ImovelComodidadesSection from "@/components/imovel/ImovelComodidadesSection";
import ImovelComodosSection from "@/components/imovel/ImovelComodosSection";
import ImovelCondicoesComerciaisSection from "@/components/imovel/ImovelCondicoesComerciaisSection";
import ImovelConstrucaoSection from "@/components/imovel/ImovelConstrucaoSection";
import ImovelDescricaoSection from "@/components/imovel/ImovelDescricaoSection";
import ImovelDocumentosCard from "@/components/imovel/ImovelDocumentosCard";
import ImovelLocalizacaoSection from "@/components/imovel/ImovelLocalizacaoSection";
import ImovelMetadadosSection from "@/components/imovel/ImovelMetadadosSection";
import ImovelMidiaSection from "@/components/imovel/ImovelMidiaSection";
import ImovelRegistroSection from "@/components/imovel/ImovelRegistroSection";
import ImovelValoresSection from "@/components/imovel/ImovelValoresSection";
import {
  useSolicitacaoDoImovel,
  useSolicitarCampanha,
} from "@/hooks/useCampanhas";
import {
  useImovelDados,
  useImovelDadosMutation,
  useImovelDocumentoMutations,
  useImovelDocumentos,
} from "@/hooks/useImovelDados";
import { useTeamMembers } from "@/hooks/useTeam";
import { formatValor, useImovel } from "@/hooks/useImoveis";

export default function ImovelDetalhes() {
  const { codigo } = useParams<{ codigo: string }>();
  const query = useImovel(codigo ?? null);
  const solicitacao = useSolicitacaoDoImovel(codigo ?? null);
  const solicitar = useSolicitarCampanha(codigo ?? null);
  const [erroSolicitacao, setErroSolicitacao] = useState<string | null>(null);

  // Cartório data + documents (migration 075). Hooks are unconditional and
  // gated on `codigo` internally — an early `return` for the loading/error
  // branches below sits BETWEEN these and the render, so calling them
  // conditionally would break the rules-of-hooks ordering.
  const dadosQuery = useImovelDados(codigo ?? null);
  const documentosQuery = useImovelDocumentos(codigo ?? null);
  const dadosMutation = useImovelDadosMutation(codigo ?? "");
  const documentoMutations = useImovelDocumentoMutations(codigo ?? "");
  const teamQuery = useTeamMembers();

  // First load only — `isPending && !data`, not `|| isFetching`. This is the
  // ENTIRE detail page; the old gate replaced header/ficha/sidebar with a
  // skeleton on every background refetch of `query` (e.g. window refocus),
  // collapsing then restoring the whole layout under the user.
  const loading = query.isPending && !query.data;
  const imovel = query.data;

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="aspect-[16/9] w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    );
  }

  if (query.isError || !imovel) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <AlertCircle className="h-10 w-10 text-destructive" />
            <p className="font-medium">Imóvel {codigo} não encontrado.</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Ele pode não ter sido sincronizado ainda. Volte ao catálogo e
              execute uma sincronização.
            </p>
            <Button asChild variant="outline">
              <Link to="/imoveis">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Voltar aos imóveis
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const endereco = [imovel.logradouro, imovel.numero, imovel.complemento]
    .filter(Boolean)
    .join(", ");
  const jaSolicitado = Boolean(solicitacao.data?.id);
  const carregandoSolicitacao =
    solicitacao.isPending || solicitacao.isFetching;

  return (
    <div className="space-y-6 p-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link to="/imoveis">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Imóveis
        </Link>
      </Button>

      {/* ── § 5.1 Cabeçalho ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{imovel.codigo}</Badge>
            {imovel.status && <Badge>{imovel.status}</Badge>}
            {imovel.categoria && <Badge variant="outline">{imovel.categoria}</Badge>}
            {imovel.exclusivo && <Badge variant="outline">Exclusivo</Badge>}
            {imovel.destaque_web && (
              <Badge variant="outline" className="gap-1">
                <Star className="h-3 w-3" />
                Destaque
              </Badge>
            )}
            {imovel.super_destaque_web && (
              <Badge variant="outline" className="gap-1">
                <Sparkles className="h-3 w-3" />
                Super destaque
              </Badge>
            )}
            {imovel.tour_360 && <Badge variant="outline">Tour 360°</Badge>}
            <EditPlaceholderButton label="Editar cabeçalho" />
          </div>
          <h1 className="max-w-3xl text-2xl font-semibold tracking-tight">
            {imovel.titulo ?? imovel.categoria ?? imovel.codigo}
          </h1>
          {(endereco || imovel.bairro || imovel.cidade) && (
            <p className="flex items-center gap-1 text-sm text-muted-foreground">
              {[endereco, imovel.bairro, imovel.cidade, imovel.uf]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>

        <div className="text-right">
          {imovel.valor_venda !== null && (
            <p className="text-2xl font-semibold">{formatValor(imovel.valor_venda)}</p>
          )}
          {imovel.valor_locacao !== null && (
            <p className="text-sm text-muted-foreground">
              {formatValor(imovel.valor_locacao)}/mês
            </p>
          )}
          {imovel.valor_venda === null && imovel.valor_locacao === null && (
            <p className="text-lg text-muted-foreground">Sob consulta</p>
          )}

          {/*
            Solicitar campanha — the signal, not a campaign. Pressing it
            says "this imóvel deserves paid traffic"; budget, channel and
            dates belong to whoever decides them.

            Disabled while the pending-state is still loading, so the page
            never offers an action that would immediately 409. Gated on
            `isPending || isFetching`, never `isLoading` — v5's isLoading
            is false during a background refetch, which would flash the
            button back to "solicitar" over a request that already exists.
          */}
          <div className="mt-4 flex flex-col items-end gap-1">
            <Button
              variant={jaSolicitado ? "secondary" : "default"}
              size="sm"
              disabled={jaSolicitado || carregandoSolicitacao || solicitar.isPending}
              onClick={() => {
                setErroSolicitacao(null);
                solicitar.mutate(undefined, {
                  onError: (err) =>
                    setErroSolicitacao(
                      err instanceof Error
                        ? err.message
                        : "Não foi possível registrar a solicitação.",
                    ),
                });
              }}
            >
              <Megaphone className="mr-2 h-4 w-4" />
              {jaSolicitado ? "Campanha solicitada" : "Solicitar campanha"}
            </Button>
            {erroSolicitacao && (
              <p className="max-w-xs text-right text-xs text-destructive">
                {erroSolicitacao}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Photo ── */}
      {imovel.foto_destaque && (
        <img
          src={imovel.foto_destaque}
          alt={imovel.titulo ?? imovel.codigo}
          className="aspect-[16/9] w-full rounded-lg object-cover"
        />
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* § 5.2 Descrição */}
          <ImovelDescricaoSection descricaoWeb={imovel.descricao_web} />

          {/* § 5.3 Valores e custos */}
          <ImovelValoresSection
            valorVenda={imovel.valor_venda}
            valorLocacao={imovel.valor_locacao}
            valorCondominio={imovel.valor_condominio}
            valorIptu={imovel.valor_iptu}
          />

          {/* § 5.4 Cômodos */}
          <ImovelComodosSection
            dormitorios={imovel.dormitorios}
            suites={imovel.suites}
            vagas={imovel.vagas}
            banheiroSocial={imovel.banheiro_social}
            closet={imovel.closet}
          />

          {/* § 5.5 Áreas */}
          <ImovelAreasSection
            areaTotal={imovel.area_total}
            areaPrivativa={imovel.area_privativa}
            areaConstruida={imovel.area_construida}
            areaTerreno={imovel.area_terreno}
            frente={imovel.frente}
            fundos={imovel.fundos}
          />

          {/* § 5.6 Construção e estado */}
          <ImovelConstrucaoSection
            anoConstrucao={imovel.ano_construcao}
            situacao={imovel.situacao}
            ocupacao={imovel.ocupacao}
            pavimentos={imovel.pavimentos}
            posicao={imovel.posicao}
            elevador={imovel.elevador}
            portaria={imovel.portaria}
          />

          {/* § 5.7 Condições comerciais */}
          <ImovelCondicoesComerciaisSection
            aceitaPermuta={imovel.aceita_permuta}
            aceitaFinanciamento={imovel.aceita_financiamento}
            exclusivo={imovel.exclusivo}
            chave={imovel.chave}
            finalidades={imovel.finalidades}
            exibirNoSite={imovel.exibir_no_site}
            destaqueWeb={imovel.destaque_web}
            superDestaqueWeb={imovel.super_destaque_web}
          />

          {/* § 5.8 Comodidades */}
          <ImovelComodidadesSection
            caracteristicas={imovel.caracteristicas}
            orientacaoSolar={imovel.orientacao_solar}
          />

          {/* § 5.9 Mídia */}
          <ImovelMidiaSection
            fotoDestaque={imovel.foto_destaque}
            tour360={imovel.tour_360}
            videoDestaque={imovel.video_destaque}
          />
        </div>

        {/* ── Sidebar ── */}
        <div className="space-y-6">
          {/* § 5.10 Localização */}
          <ImovelLocalizacaoSection
            endereco={endereco}
            cep={imovel.cep}
            bairro={imovel.bairro}
            cidade={imovel.cidade}
            uf={imovel.uf}
            zona={imovel.zona}
            regiao={imovel.regiao}
            empreendimento={imovel.empreendimento}
            construtora={imovel.construtora}
            latitude={imovel.latitude}
            longitude={imovel.longitude}
          />

          {/* § 5.11 Corretores — existing block, unchanged. */}
          {imovel.corretores.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {imovel.corretores.length > 1 ? "Corretores" : "Corretor"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {imovel.corretores.map((c, i) => (
                  <div key={c.codigo ?? i} className="space-y-1">
                    <p className="text-sm font-medium">{c.nome ?? "—"}</p>
                    {c.email && (
                      <a
                        href={`mailto:${c.email}`}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:underline"
                      >
                        <Mail className="h-3 w-3" />
                        {c.email}
                      </a>
                    )}
                    {c.fone && <p className="text-xs text-muted-foreground">{c.fone}</p>}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* § 5.12 Registro, then the existing ImovelCartorioCard beneath
              it — the cartório-authored record stays a separate, real
              (non-placeholder) editor; only the Vista-sourced facts above
              it get the display-only Pencil. */}
          <ImovelRegistroSection
            matriculaVista={imovel.matricula_vista}
            inscricaoMunicipal={imovel.inscricao_municipal}
            codigoImobiliaria={imovel.codigo_imobiliaria}
            referencia={imovel.referencia}
          />

          {/* What WE author about this property — never the Vista mirror.
              See migration 075 for why the two are separate. */}
          <ImovelCartorioCard
            dados={dadosQuery.data}
            membros={teamQuery.data ?? []}
            loading={dadosQuery.isPending && !dadosQuery.data}
            saving={dadosMutation.isPending}
            error={dadosMutation.error?.message ?? null}
            onSave={(patch) => dadosMutation.mutate(patch)}
          />

          <ImovelDocumentosCard
            documentos={documentosQuery.data ?? []}
            loading={documentosQuery.isPending && !documentosQuery.data}
            uploading={documentoMutations.upload.isPending}
            error={
              documentoMutations.upload.error?.message ??
              documentoMutations.remove.error?.message ??
              null
            }
            onUpload={(file, tipoDocumento) =>
              documentoMutations.upload.mutate({ file, tipoDocumento })
            }
            onRemove={(documentoId, motivo) =>
              documentoMutations.remove.mutate({ documentoId, motivo })
            }
            onOpen={async (documentoId) => {
              const res = await documentoMutations.getUrl.mutateAsync(documentoId);
              // `noopener` — a signed URL opened into a tab that keeps a
              // handle on this one is a needless cross-window reference.
              if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
            }}
          />

          {/* § 5.13 Metadados */}
          <ImovelMetadadosSection
            dataCadastro={imovel.data_cadastro}
            dataAtualizacao={imovel.data_atualizacao}
            diasDesdeAtualizacao={imovel.dias_desde_atualizacao}
            sincronizadoEm={imovel.sincronizado_em}
          />
        </div>
      </div>
    </div>
  );
}
