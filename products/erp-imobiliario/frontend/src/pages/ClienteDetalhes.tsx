import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useCliente, useToggleArquivarCliente } from '@/hooks/useClientes';
import { useMoverClienteEtapa } from '@/hooks/useFunil';
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
import { ETAPAS_CONFIG } from '@/lib/etapasConfig';
import { EtapaFunil } from '@/types/clientes';
import { Archive, UserX } from 'lucide-react';

const ETAPAS = Object.entries(ETAPAS_CONFIG) as [EtapaFunil, (typeof ETAPAS_CONFIG)[EtapaFunil]][];

export default function ClienteDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: cliente, isLoading } = useCliente(id);
  const { mutate: toggleArquivar } = useToggleArquivarCliente();
  const { mutate: moverEtapa } = useMoverClienteEtapa();

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

  const etapaConfig = ETAPAS_CONFIG[cliente.etapa_atual];

  const handleMoverEtapa = (novaEtapa: string) => {
    if (novaEtapa === cliente.etapa_atual) return;
    moverEtapa({
      cliente_id: cliente.id,
      para_etapa: novaEtapa as EtapaFunil,
    });
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
              <Badge className={etapaConfig.bgColor}>{etapaConfig.label}</Badge>
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
            <Select value={cliente.etapa_atual} onValueChange={handleMoverEtapa}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ETAPAS.map(([value, config]) => (
                  <SelectItem key={value} value={value}>
                    {config.label}
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
