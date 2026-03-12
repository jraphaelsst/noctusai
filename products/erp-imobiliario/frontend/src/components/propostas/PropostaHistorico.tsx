import { Card } from '@/components/ui/card';
import { formatCurrency, formatDate } from '@/lib/utils';
import { HistoricoProposta } from '@/types/propostas';

interface PropostaHistoricoProps {
  historico: HistoricoProposta[];
}

export function PropostaHistorico({ historico }: PropostaHistoricoProps) {
  if (!historico || historico.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Nenhum histórico disponível</p>
      </Card>
    );
  }

  return (
    <Card className="p-4 sm:p-6">
      <div className="space-y-4">
        {historico.map((entry, index) => (
          <div key={index} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className="w-2 h-2 bg-primary rounded-full mt-2" />
              {index < historico.length - 1 && (
                <div className="w-px flex-1 bg-border mt-1" />
              )}
            </div>
            <div className="flex-1 pb-4">
              <p className="font-medium text-sm">{entry.action}</p>
              <p className="text-xs text-muted-foreground">
                {formatDate(entry.timestamp, true)}
              </p>
              {entry.details && (
                <div className="mt-1 text-xs text-muted-foreground">
                  {Object.entries(entry.details).map(([key, value]) => (
                    <span key={key} className="block">
                      {key}: {typeof value === 'number' ? formatCurrency(value) : String(value)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
