import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { useCliente, useToggleArquivarCliente } from '@/hooks/useClientes';
import { useNegociacoesDoCliente } from '@/hooks/useFunil';
import { funilPipeline } from '@/lib/pipelines';
import { stageColorClasses } from '@noctusai/lib/components';
import { LeadScoreBadge } from '@/components/clientes/LeadScoreBadge';
import { AIIndicator } from '@noctusai/lib/design-system';
import { ClienteResumo } from '@/components/clientes/ClienteResumo';
import { ClienteAtividades } from '@/components/clientes/ClienteAtividades';
import { ClientePropostas } from '@/components/clientes/ClientePropostas';
import { ClienteDocumentos } from '@/components/clientes/ClienteDocumentos';
import { ClienteHistorico } from '@/components/clientes/ClienteHistorico';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Archive, UserX } from 'lucide-react';


export default function ClienteDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: cliente, isLoading } = useCliente(id);
  const { mutate: toggleArquivar } = useToggleArquivarCliente();
  const { mutate: moverNegociacao } = funilPipeline.useMoveCard();
  const { data: etapasFunil } = funilPipeline.useStages();
  const { data: negociacoesAbertas } = useNegociacoesDoCliente(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!cliente) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={UserX}
          title="Cliente não encontrado"
          action={{ label: 'Voltar para Clientes', onClick: () => navigate('/clientes') }}
        />
      </div>
    );
  }

  // The stage lives on the DEAL, not the cliente (roadmap P1.5.4).
  // `clientes.etapa_atual` is written-but-ignored for one release, so reading
  // it here would show a stage the Funil no longer honours.
  //
  // A cliente can hold several concurrent deals, and this page has no way to
  // know which one the user means — so the control acts on the deal only when
  // there is exactly ONE open. With none, or with several, it goes read-only
  // and points at the Funil rather than guessing.
  const negociacoes = negociacoesAbertas ?? [];
  const negociacaoUnica = negociacoes.length === 1 ? negociacoes[0] : null;
  // The stage comes from the joined stage row, not a hardcoded config map —
  // stages are user-editable, so the label and colour must be read, not looked
  // up by slug.
  const etapaAtual = negociacaoUnica?.etapa_rel ?? null;
  const etapaClasses = etapaAtual ? stageColorClasses(etapaAtual.cor) : null;
  const etapasOrdenadas = [...(etapasFunil ?? [])].sort((a, b) => a.posicao - b.posicao);

  const handleMoverEtapa = (novaEtapaId: string) => {
    if (!negociacaoUnica || novaEtapaId === negociacaoUnica.etapa_id) return;
    moverNegociacao({ cardId: negociacaoUnica.id, toStageId: novaEtapaId });
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Clientes', href: '/clientes' },
        { label: cliente.nome },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold truncate">{cliente.nome}</h1>
              {etapaAtual ? (
                <Badge className={etapaClasses!.bgColor}>{etapaAtual.label}</Badge>
              ) : negociacoes.length > 1 ? (
                <Badge variant="secondary">{negociacoes.length} negociações abertas</Badge>
              ) : (
                <Badge variant="outline">Sem negociação aberta</Badge>
              )}
              {cliente.arquivado && <Badge variant="secondary">Arquivado</Badge>}
              <LeadScoreBadge cliente={cliente} />
              <AIIndicator refType="cliente" refId={cliente.id} showAll enableFeedback />
            </div>
            {cliente.usuario && (
              <p className="text-sm text-muted-foreground">
                Responsável: {cliente.usuario.nome}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <Select
              value={negociacaoUnica?.etapa_id ?? ''}
              onValueChange={handleMoverEtapa}
              disabled={!negociacaoUnica}
            >
              <SelectTrigger
                className="w-[180px]"
                title={
                  negociacaoUnica
                    ? undefined
                    : negociacoes.length > 1
                      ? 'Este cliente tem várias negociações abertas — mova a etapa no Funil de Vendas.'
                      : 'Este cliente não tem negociação aberta.'
                }
              >
                <SelectValue placeholder="Sem negociação aberta" />
              </SelectTrigger>
              <SelectContent>
                {etapasOrdenadas.map((etapa) => (
                  <SelectItem key={etapa.id} value={etapa.id}>
                    {etapa.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              onClick={() => toggleArquivar(cliente.id)}
            >
              <Archive className="w-4 h-4 mr-2" />
              {cliente.arquivado ? 'Desarquivar' : 'Arquivar'}
            </Button>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="atividades">Atividades</TabsTrigger>
          <TabsTrigger value="propostas">Propostas</TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
          <TabsTrigger value="historico">Histórico</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <ClienteResumo cliente={cliente} />
        </TabsContent>

        <TabsContent value="atividades" className="mt-6">
          <ClienteAtividades clienteId={cliente.id} />
        </TabsContent>

        <TabsContent value="propostas" className="mt-6">
          <ClientePropostas clienteId={cliente.id} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-6">
          <ClienteDocumentos clienteId={cliente.id} />
        </TabsContent>

        <TabsContent value="historico" className="mt-6">
          <ClienteHistorico clienteId={cliente.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
