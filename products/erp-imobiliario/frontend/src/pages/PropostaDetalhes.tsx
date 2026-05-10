import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { useProposta } from '@/hooks/usePropostas';
import { PropostaResumo } from '@/components/propostas/PropostaResumo';
import { PropostaHistorico } from '@/components/propostas/PropostaHistorico';
import { PropostaDocumentos } from '@/components/propostas/PropostaDocumentos';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { formatCurrency } from '@/lib/utils';
import { StatusProposta } from '@/types/propostas';
import { FileX } from 'lucide-react';

const STATUS_CONFIG: Record<StatusProposta, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  enviada: { label: 'Enviada', variant: 'outline' },
  em_analise: { label: 'Em Análise', variant: 'secondary' },
  contraproposta: { label: 'Contraproposta', variant: 'default' },
  aceita: { label: 'Aceita', variant: 'default' },
  recusada: { label: 'Recusada', variant: 'destructive' },
  expirada: { label: 'Expirada', variant: 'secondary' },
};

export default function PropostaDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: proposta, isLoading } = useProposta(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!proposta) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Proposta não encontrada"
          action={{ label: 'Voltar para Propostas', onClick: () => navigate('/propostas') }}
        />
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[proposta.status];

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Propostas', href: '/propostas' },
        { label: `Proposta #${proposta.id.slice(0, 8)}` },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold">
                Proposta #{proposta.id.slice(0, 8)}
              </h1>
              <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
            </div>
            {proposta.prazo_validade && (
              <p className="text-sm text-muted-foreground">
                Validade: {proposta.prazo_validade}
              </p>
            )}
          </div>

          <div className="text-right">
            <p className="text-2xl sm:text-3xl font-bold text-primary">
              {formatCurrency(proposta.valor_proposta)}
            </p>
            {proposta.valor_contraproposta && (
              <p className="text-lg font-semibold text-orange-600">
                Contra: {formatCurrency(proposta.valor_contraproposta)}
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="historico">Histórico</TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <PropostaResumo proposta={proposta} />
        </TabsContent>

        <TabsContent value="historico" className="mt-6">
          <PropostaHistorico historico={proposta.historico} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-6">
          <PropostaDocumentos propostaId={proposta.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
