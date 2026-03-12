import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useLocacao } from '@/hooks/useLocacoes';
import { LocacaoResumo } from '@/components/locacoes/LocacaoResumo';
import { LocacaoVistorias } from '@/components/locacoes/LocacaoVistorias';
import { LocacaoDocumentos } from '@/components/locacoes/LocacaoDocumentos';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { StatusLocacao } from '@/types/locacoes';
import { FileX } from 'lucide-react';

const STATUS_CONFIG: Record<StatusLocacao, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  ativo: { label: 'Ativo', variant: 'default' },
  encerrado: { label: 'Encerrado', variant: 'secondary' },
  renovado: { label: 'Renovado', variant: 'outline' },
  inadimplente: { label: 'Inadimplente', variant: 'destructive' },
};

export default function LocacaoDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: locacao, isLoading } = useLocacao(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!locacao) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Locação não encontrada"
          action={{ label: 'Voltar para Locações', onClick: () => navigate('/locacoes') }}
        />
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[locacao.status] || STATUS_CONFIG.ativo;

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Locações', href: '/locacoes' },
        { label: `Locação #${locacao.id.slice(0, 8)}` },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold">
                Locação #{locacao.id.slice(0, 8)}
              </h1>
              <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
              <Badge variant="outline">{locacao.indice_reajuste}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(locacao.data_inicio)} — {formatDate(locacao.data_fim)}
            </p>
          </div>

          <div className="text-right">
            <p className="text-2xl sm:text-3xl font-bold text-primary">
              {formatCurrency(locacao.valor_aluguel)}
            </p>
            <p className="text-sm text-muted-foreground">por mês</p>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="vistorias">Vistorias</TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <LocacaoResumo locacao={locacao} />
        </TabsContent>

        <TabsContent value="vistorias" className="mt-6">
          <LocacaoVistorias imovelId={locacao.imovel_id} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-6">
          <LocacaoDocumentos imovelId={locacao.imovel_id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
