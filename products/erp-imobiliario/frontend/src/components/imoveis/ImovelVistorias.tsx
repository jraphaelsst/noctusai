import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { useVistorias } from '@/hooks/useVistorias';
import { TipoVistoria, StatusVistoria } from '@/types/locacoes';
import { formatDate } from '@/lib/utils';
import { VISTORIA_STATUS_CONFIG } from '@/lib/constants';
import { ClipboardCheck } from 'lucide-react';

const TIPO_CONFIG: Record<TipoVistoria, { label: string; className: string }> = {
  entrada: { label: 'Entrada', className: 'bg-blue-100 text-blue-800' },
  saida: { label: 'Saída', className: 'bg-orange-100 text-orange-800' },
  periodica: { label: 'Periódica', className: 'bg-gray-100 text-gray-800' },
};

interface ImovelVistoriasProps {
  imovelId: string;
}

export function ImovelVistorias({ imovelId }: ImovelVistoriasProps) {
  const { data: vistorias = [], isLoading } = useVistorias({ imovel_id: imovelId });

  if (isLoading) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando vistorias...</p>
      </Card>
    );
  }

  if (vistorias.length === 0) {
    return (
      <Card className="p-8 text-center">
        <ClipboardCheck className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">Nenhuma vistoria encontrada para este imóvel</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {vistorias.map((vistoria) => {
        const tipoConfig = TIPO_CONFIG[vistoria.tipo];
        const statusConfig = VISTORIA_STATUS_CONFIG[vistoria.status];
        return (
          <Card key={vistoria.id} className="p-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className={tipoConfig.className}>
                    {tipoConfig.label}
                  </Badge>
                  <Badge variant="outline" className={statusConfig.color}>
                    {statusConfig.label}
                  </Badge>
                </div>
                {vistoria.responsavel_nome && (
                  <p className="text-sm text-muted-foreground">
                    Responsável: {vistoria.responsavel_nome}
                  </p>
                )}
              </div>

              <div className="text-sm text-muted-foreground text-right">
                <p>Data: {formatDate(vistoria.data_vistoria)}</p>
              </div>
            </div>

            {vistoria.resumo_checklist && Object.keys(vistoria.resumo_checklist).length > 0 && (
              <div className="mt-2 pt-2 border-t flex flex-wrap gap-2">
                {Object.entries(vistoria.resumo_checklist).map(([estado, count]) => (
                  <span key={estado} className="text-xs text-muted-foreground">
                    {estado}: {count}
                  </span>
                ))}
              </div>
            )}

            {vistoria.observacoes_gerais && (
              <p className="text-sm text-muted-foreground mt-2 pt-2 border-t">
                {vistoria.observacoes_gerais}
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}
