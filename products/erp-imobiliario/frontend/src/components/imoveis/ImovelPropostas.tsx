import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { usePropostas } from '@/hooks/usePropostas';
import { formatCurrency, formatDate } from '@/lib/utils';
import { PROPOSTA_STATUS_CONFIG } from '@/lib/constants';
import { FileText } from 'lucide-react';

interface ImovelPropostasProps {
  imovelId: string;
}

export function ImovelPropostas({ imovelId }: ImovelPropostasProps) {
  const { data: result, isLoading } = usePropostas({ imovel_id: imovelId });
  const propostas = result?.data || [];

  if (isLoading) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando propostas...</p>
      </Card>
    );
  }

  if (propostas.length === 0) {
    return (
      <Card className="p-8 text-center">
        <FileText className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">Nenhuma proposta encontrada para este imóvel</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {propostas.map((proposta) => {
        const statusConfig = PROPOSTA_STATUS_CONFIG[proposta.status];
        return (
          <Card key={proposta.id} className="p-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-lg font-semibold">
                    {formatCurrency(proposta.valor_proposta)}
                  </p>
                  <Badge variant="outline" className={statusConfig.color}>
                    {statusConfig.label}
                  </Badge>
                </div>
                {proposta.valor_contraproposta && (
                  <p className="text-sm text-muted-foreground">
                    Contraproposta: {formatCurrency(proposta.valor_contraproposta)}
                  </p>
                )}
                {proposta.condicoes_pagamento && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {proposta.condicoes_pagamento}
                  </p>
                )}
              </div>

              <div className="text-sm text-muted-foreground text-right">
                <p>Criada em {formatDate(proposta.created_at)}</p>
                {proposta.prazo_validade && (
                  <p>Validade: {formatDate(proposta.prazo_validade)}</p>
                )}
              </div>
            </div>

            {proposta.observacoes && (
              <p className="text-sm text-muted-foreground mt-2 pt-2 border-t">
                {proposta.observacoes}
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}
