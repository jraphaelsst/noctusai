import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useContrato } from '@/hooks/useContratos';
import { ContratoResumo } from '@/components/contratos/ContratoResumo';
import { ContratoParcelas } from '@/components/contratos/ContratoParcelas';
import { ContratoDocumentos } from '@/components/contratos/ContratoDocumentos';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { formatCurrency, formatDate } from '@/lib/utils';
import { CONTRATO_STATUS_CONFIG, CONTRATO_TIPO_CONFIG } from '@/lib/constants';
import { TipoContrato, StatusContrato } from '@/types/contratos';
import { FileX } from 'lucide-react';

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  rascunho: 'outline',
  ativo: 'default',
  concluido: 'secondary',
  cancelado: 'destructive',
  distratado: 'destructive',
};

const TIPO_CLASS: Record<string, string> = {
  venda: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  locacao: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
};

export default function ContratoDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: contrato, isLoading } = useContrato(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!contrato) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Contrato não encontrado"
          action={{ label: 'Voltar para Contratos', onClick: () => navigate('/contratos') }}
        />
      </div>
    );
  }

  const statusConfig = {
    label: CONTRATO_STATUS_CONFIG[contrato.status]?.label || contrato.status,
    variant: STATUS_VARIANT[contrato.status] || 'outline' as const,
  };
  const tipoConfig = {
    label: CONTRATO_TIPO_CONFIG[contrato.tipo]?.label || contrato.tipo,
    className: TIPO_CLASS[contrato.tipo] || '',
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Contratos', href: '/contratos' },
        { label: `Contrato #${contrato.id.slice(0, 8)}` },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold">
                Contrato #{contrato.id.slice(0, 8)}
              </h1>
              <Badge className={tipoConfig.className}>{tipoConfig.label}</Badge>
              <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(contrato.data_inicio)}
              {contrato.data_fim ? ` — ${formatDate(contrato.data_fim)}` : ''}
            </p>
          </div>

          <div className="text-right">
            <p className="text-2xl sm:text-3xl font-bold text-primary">
              {formatCurrency(contrato.valor_total)}
            </p>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="parcelas">Parcelas</TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <ContratoResumo contrato={contrato} />
        </TabsContent>

        <TabsContent value="parcelas" className="mt-6">
          <ContratoParcelas contratoId={contrato.id} valorTotal={contrato.valor_total} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-6">
          <ContratoDocumentos imovelId={contrato.imovel_id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
