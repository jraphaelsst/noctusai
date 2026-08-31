import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { useVistoria } from '@/hooks/useVistorias';
import { VistoriaResumo } from '@/components/vistorias/VistoriaResumo';
import { VistoriaChecklist } from '@/components/vistorias/VistoriaChecklist';
import { VistoriaFotos } from '@/components/vistorias/VistoriaFotos';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { formatDate } from '@/lib/utils';
import { VISTORIA_STATUS_CONFIG, VISTORIA_TIPO_CONFIG } from '@/lib/constants';
import type { TipoVistoria, StatusVistoria } from '@/types/locacoes';
import { Calendar, CheckCircle, Clock, XCircle, FileX } from 'lucide-react';

const TIPO_VARIANT: Record<TipoVistoria, 'default' | 'secondary' | 'outline'> = {
  entrada: 'default',
  saida: 'secondary',
  periodica: 'outline',
};

const STATUS_ICON: Record<StatusVistoria, { icon: typeof Clock; color: string }> = {
  agendada: { icon: Calendar, color: 'text-blue-500' },
  em_andamento: { icon: Clock, color: 'text-yellow-500' },
  concluida: { icon: CheckCircle, color: 'text-green-500' },
  cancelada: { icon: XCircle, color: 'text-red-500' },
};

export default function VistoriaDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const vistoriaQuery = useVistoria(id);
  const { data: vistoria } = vistoriaQuery;

  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  if (vistoriaQuery.isPending && !vistoriaQuery.data) return <DetailPageSkeleton />;

  if (!vistoria) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Vistoria não encontrada"
          action={{ label: 'Voltar para Vistorias', onClick: () => navigate('/vistorias') }}
        />
      </div>
    );
  }

  const tipoLabel = VISTORIA_TIPO_CONFIG[vistoria.tipo]?.label || vistoria.tipo;
  const tipoVariant = TIPO_VARIANT[vistoria.tipo] || 'default';
  const statusLabel = VISTORIA_STATUS_CONFIG[vistoria.status]?.label || vistoria.status;
  const statusIcon = STATUS_ICON[vistoria.status] || STATUS_ICON.agendada;
  const StatusIcon = statusIcon.icon;
  const isReadOnly = vistoria.status === 'concluida' || vistoria.status === 'cancelada';

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Vistorias', href: '/vistorias' },
        { label: `Vistoria #${vistoria.id.slice(0, 8)}` },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold">
                Vistoria #{vistoria.id.slice(0, 8)}
              </h1>
              <Badge variant={tipoVariant}>{tipoLabel}</Badge>
              <div className={`flex items-center gap-1 ${statusIcon.color}`}>
                <StatusIcon className="w-4 h-4" />
                <span className="font-medium">{statusLabel}</span>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(vistoria.data_vistoria)}
              {vistoria.responsavel_nome && ` — ${vistoria.responsavel_nome}`}
            </p>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="checklist">Checklist</TabsTrigger>
          <TabsTrigger value="fotos">Fotos</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <VistoriaResumo vistoria={vistoria} />
        </TabsContent>

        <TabsContent value="checklist" className="mt-6">
          <VistoriaChecklist
            vistoriaId={vistoria.id}
            checklist={vistoria.checklist}
            readOnly={isReadOnly}
          />
        </TabsContent>

        <TabsContent value="fotos" className="mt-6">
          <VistoriaFotos fotos={vistoria.fotos} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
