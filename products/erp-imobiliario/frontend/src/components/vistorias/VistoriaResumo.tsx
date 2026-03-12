import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { EntityLink } from '@/components/ui/entity-link';
import { useUpdateVistoria } from '@/hooks/useVistorias';
import { formatDate } from '@/lib/utils';
import { VISTORIA_TIPO_CONFIG } from '@/lib/constants';
import type { Vistoria, StatusVistoria, TipoVistoria } from '@/types/locacoes';
import { Calendar, User, Home, Play, CheckCircle, XCircle } from 'lucide-react';

interface VistoriaResumoProps {
  vistoria: Vistoria;
}

export function VistoriaResumo({ vistoria }: VistoriaResumoProps) {
  const { mutate: updateVistoria } = useUpdateVistoria();

  const handleStatusChange = (newStatus: StatusVistoria) => {
    updateVistoria({ id: vistoria.id, status: newStatus });
  };

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Calendar className="w-4 h-4" />
            <span className="text-sm">Data</span>
          </div>
          <p className="text-lg font-bold">{formatDate(vistoria.data_vistoria)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Home className="w-4 h-4" />
            <span className="text-sm">Tipo</span>
          </div>
          <p className="text-lg font-bold">{VISTORIA_TIPO_CONFIG[vistoria.tipo]?.label || vistoria.tipo}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <User className="w-4 h-4" />
            <span className="text-sm">Responsável</span>
          </div>
          <p className="text-lg font-medium truncate">{vistoria.responsavel_nome || '-'}</p>
        </Card>
        {vistoria.checklist && vistoria.checklist.length > 0 && (
          <Card className="p-4">
            <div className="text-muted-foreground mb-1 text-sm">Checklist</div>
            <p className="text-lg font-bold">{vistoria.checklist.length} itens</p>
          </Card>
        )}
      </div>

      {/* Info Grid */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Informações</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <Label className="text-muted-foreground text-xs">Imóvel</Label>
            <p><EntityLink type="imovel" id={vistoria.imovel_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Responsável</Label>
            <p><EntityLink type="cliente" id={vistoria.responsavel_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Criada em</Label>
            <p>{formatDate(vistoria.created_at)}</p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Atualizada em</Label>
            <p>{formatDate(vistoria.updated_at)}</p>
          </div>
          {vistoria.observacoes_gerais && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Observações Gerais</Label>
              <p className="whitespace-pre-wrap">{vistoria.observacoes_gerais}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Checklist Summary */}
      {vistoria.resumo_checklist && Object.keys(vistoria.resumo_checklist).length > 0 && (
        <Card className="p-4 sm:p-6">
          <h3 className="text-lg font-semibold mb-3">Resumo do Checklist</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(vistoria.resumo_checklist).map(([estado, count]) => (
              <Badge key={estado} variant="outline">
                {estado}: {count}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Status Actions */}
      {(vistoria.status === 'agendada' || vistoria.status === 'em_andamento') && (
        <Card className="p-4 sm:p-6">
          <h3 className="text-lg font-semibold mb-3">Ações</h3>
          <div className="flex flex-wrap gap-2">
            {vistoria.status === 'agendada' && (
              <Button variant="outline" onClick={() => handleStatusChange('em_andamento')}>
                <Play className="w-4 h-4 mr-2" />
                Iniciar Vistoria
              </Button>
            )}
            {vistoria.status === 'em_andamento' && (
              <Button variant="outline" className="text-green-600" onClick={() => handleStatusChange('concluida')}>
                <CheckCircle className="w-4 h-4 mr-2" />
                Concluir Vistoria
              </Button>
            )}
            <Button variant="outline" className="text-red-600" onClick={() => handleStatusChange('cancelada')}>
              <XCircle className="w-4 h-4 mr-2" />
              Cancelar
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
