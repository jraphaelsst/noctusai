import { useNavigate } from 'react-router-dom';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { useVistorias } from '@/hooks/useVistorias';
import { formatDate } from '@/lib/utils';
import { ClipboardCheck, Calendar, Eye } from 'lucide-react';
import type { TipoVistoria, StatusVistoria } from '@/types/locacoes';

const TIPO_CONFIG: Record<TipoVistoria, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  entrada: { label: 'Entrada', variant: 'default' },
  saida: { label: 'Saída', variant: 'secondary' },
  periodica: { label: 'Periódica', variant: 'outline' },
};

const STATUS_CONFIG: Record<StatusVistoria, { label: string; color: string }> = {
  agendada: { label: 'Agendada', color: 'text-blue-500' },
  em_andamento: { label: 'Em Andamento', color: 'text-yellow-500' },
  concluida: { label: 'Concluída', color: 'text-green-500' },
  cancelada: { label: 'Cancelada', color: 'text-red-500' },
};

interface LocacaoVistoriasProps {
  imovelId: string;
}

export function LocacaoVistorias({ imovelId }: LocacaoVistoriasProps) {
  const navigate = useNavigate();
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
        const tipoCfg = TIPO_CONFIG[vistoria.tipo] || TIPO_CONFIG.entrada;
        const statusCfg = STATUS_CONFIG[vistoria.status] || STATUS_CONFIG.agendada;

        return (
          <Card key={vistoria.id} className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant={tipoCfg.variant}>{tipoCfg.label}</Badge>
                    <span className={`text-sm ${statusCfg.color}`}>{statusCfg.label}</span>
                  </div>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Calendar className="h-3 w-3" />
                    {formatDate(vistoria.data_vistoria)}
                    {vistoria.responsavel_nome && (
                      <span className="ml-2">— {vistoria.responsavel_nome}</span>
                    )}
                  </div>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate(`/vistorias/${vistoria.id}`)}>
                <Eye className="w-4 h-4 mr-1" />
                Ver
              </Button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
