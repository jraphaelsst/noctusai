/**
 * ImovelDetalhes — one imóvel, full record.
 *
 * Route: /imoveis/:codigo. Reads the local mirror; a code that was never
 * synced 404s rather than silently falling back to a live Vista call, so the
 * page never disagrees with the catalog it was reached from.
 *
 * Rendering decisions that encode measured wire facts:
 *   · The map block only renders when both coordinates exist — 36.8% of the
 *     catalog has none, so a fallback is the common path, not the edge case.
 *   · Counts use formatCount so a genuine 0 (terreno) reads "0", while
 *     unknown reads "—".
 *   · ALL corretores are listed; 13.1% of imóveis have 2-3.
 *   · `area_construida` is omitted when null, which is 99.9% of this tenant.
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Megaphone,
  Bath,
  BedDouble,
  Building2,
  Car,
  ExternalLink,
  Mail,
  MapPin,
  Ruler,
  Sofa,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import ImovelCartorioCard from "@/components/imovel/ImovelCartorioCard";
import ImovelDocumentosCard from "@/components/imovel/ImovelDocumentosCard";
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
import {
  caracteristicaLabel,
  formatArea,
  formatCount,
  formatValor,
  useImovel,
} from "@/hooks/useImoveis";

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

  const loading = query.isPending || query.isFetching;
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
  const temGeo = imovel.latitude !== null && imovel.longitude !== null;
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

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{imovel.codigo}</Badge>
            {imovel.status && <Badge>{imovel.status}</Badge>}
            {imovel.categoria && <Badge variant="outline">{imovel.categoria}</Badge>}
          </div>
          <h1 className="max-w-3xl text-2xl font-semibold tracking-tight">
            {imovel.titulo ?? imovel.categoria ?? imovel.codigo}
          </h1>
          {(endereco || imovel.bairro || imovel.cidade) && (
            <p className="flex items-center gap-1 text-sm text-muted-foreground">
              <MapPin className="h-4 w-4 shrink-0" />
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
          {/* ── Ficha ── */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Ficha técnica</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Fact icon={<BedDouble className="h-4 w-4" />} label="Dormitórios" value={formatCount(imovel.dormitorios)} />
              <Fact icon={<Sofa className="h-4 w-4" />} label="Suítes" value={formatCount(imovel.suites)} />
              <Fact icon={<Car className="h-4 w-4" />} label="Vagas" value={formatCount(imovel.vagas)} />
              <Fact
                icon={<Bath className="h-4 w-4" />}
                label="Banheiro social"
                value={
                  imovel.banheiro_social === null
                    ? "—"
                    : imovel.banheiro_social
                      ? "Sim"
                      : "Não"
                }
              />
              <Fact icon={<Ruler className="h-4 w-4" />} label="Área total" value={formatArea(imovel.area_total)} />
              <Fact icon={<Ruler className="h-4 w-4" />} label="Área privativa" value={formatArea(imovel.area_privativa)} />
              {/* Omitted rather than shown as "—": null on 99.9% of this
                  tenant's catalog, so a permanent dash is just noise. */}
              {imovel.area_construida !== null && (
                <Fact icon={<Ruler className="h-4 w-4" />} label="Área construída" value={formatArea(imovel.area_construida)} />
              )}
              {imovel.empreendimento && (
                <Fact icon={<Building2 className="h-4 w-4" />} label="Empreendimento" value={imovel.empreendimento} />
              )}
              {imovel.construtora && (
                <Fact icon={<Building2 className="h-4 w-4" />} label="Construtora" value={imovel.construtora} />
              )}
            </CardContent>
          </Card>

          {/* ── Características ── */}
          {imovel.caracteristicas.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Características ({imovel.caracteristicas.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {imovel.caracteristicas.map((slug) => (
                  <Badge key={slug} variant="secondary">
                    {caracteristicaLabel(slug)}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* ── Sidebar ── */}
        <div className="space-y-6">
          {/* What WE author about this property — never the Vista mirror.
              See migration 075 for why the two are separate. */}
          <ImovelCartorioCard
            dados={dadosQuery.data}
            membros={teamQuery.data ?? []}
            loading={dadosQuery.isPending || dadosQuery.isFetching}
            saving={dadosMutation.isPending}
            error={dadosMutation.error?.message ?? null}
            onSave={(patch) => dadosMutation.mutate(patch)}
          />

          <ImovelDocumentosCard
            documentos={documentosQuery.data ?? []}
            loading={documentosQuery.isPending || documentosQuery.isFetching}
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

          {/* ALL corretores — 13.1% of imóveis have more than one. */}
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

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Localização</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {imovel.cep && <p className="text-muted-foreground">CEP {imovel.cep}</p>}
              {temGeo ? (
                <Button asChild variant="outline" size="sm" className="w-full">
                  <a
                    href={`https://www.google.com/maps/search/?api=1&query=${imovel.latitude},${imovel.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <MapPin className="mr-2 h-4 w-4" />
                    Ver no mapa
                    <ExternalLink className="ml-2 h-3 w-3" />
                  </a>
                </Button>
              ) : (
                // The common case, not an error — 36.8% have no coordinates.
                <p className="text-xs text-muted-foreground">
                  Sem coordenadas cadastradas no Vista.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Registro</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              {imovel.codigo_imobiliaria && <p>Imobiliária: {imovel.codigo_imobiliaria}</p>}
              {imovel.data_cadastro && (
                <p>Cadastrado em {new Date(imovel.data_cadastro).toLocaleDateString("pt-BR")}</p>
              )}
              {imovel.data_atualizacao && (
                <p>Atualizado em {new Date(imovel.data_atualizacao).toLocaleDateString("pt-BR")}</p>
              )}
              {imovel.sincronizado_em && (
                <p>Sincronizado em {new Date(imovel.sincronizado_em).toLocaleString("pt-BR")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Fact({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="space-y-1">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {icon}
        {label}
      </p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}
