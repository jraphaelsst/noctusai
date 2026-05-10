import { useState } from 'react';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { EntityLink } from '@/components/ui/entity-link';
import { useUpdateProposta } from '@/hooks/usePropostas';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Proposta, StatusProposta } from '@/types/propostas';
import {
  DollarSign,
  Calendar,
  Clock,
  CheckCircle2,
  XCircle,
  ArrowRightLeft,
  Edit,
  Save,
  X,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const editSchema = z.object({
  valor_proposta: z.coerce.number().min(0),
  condicoes_pagamento: z.string().optional(),
  prazo_validade: z.string().optional(),
  observacoes: z.string().optional(),
});

type EditFormData = z.infer<typeof editSchema>;

interface PropostaResumoProps {
  proposta: Proposta;
}

export function PropostaResumo({ proposta }: PropostaResumoProps) {
  const [editando, setEditando] = useState(false);
  const { mutate: updateProposta, isPending } = useUpdateProposta();

  const canChangeStatus = !['aceita', 'recusada', 'expirada'].includes(proposta.status);

  const { register, handleSubmit, formState: { errors }, reset } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      valor_proposta: proposta.valor_proposta,
      condicoes_pagamento: proposta.condicoes_pagamento || '',
      prazo_validade: proposta.prazo_validade || '',
      observacoes: proposta.observacoes || '',
    },
  });

  const onSubmit = (data: EditFormData) => {
    updateProposta(
      {
        id: proposta.id,
        valor_proposta: data.valor_proposta,
        condicoes_pagamento: data.condicoes_pagamento || undefined,
        prazo_validade: data.prazo_validade || undefined,
        observacoes: data.observacoes || undefined,
      },
      { onSuccess: () => setEditando(false) }
    );
  };

  const handleCancel = () => {
    reset();
    setEditando(false);
  };

  const handleStatusChange = (newStatus: StatusProposta) => {
    updateProposta({ id: proposta.id, status: newStatus });
  };

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-sm">Valor Proposta</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(proposta.valor_proposta)}</p>
        </Card>
        {proposta.valor_contraproposta && (
          <Card className="p-4">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <ArrowRightLeft className="w-4 h-4" />
              <span className="text-sm">Contraproposta</span>
            </div>
            <p className="text-2xl font-bold text-orange-600">
              {formatCurrency(proposta.valor_contraproposta)}
            </p>
          </Card>
        )}
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Calendar className="w-4 h-4" />
            <span className="text-sm">Criada em</span>
          </div>
          <p className="text-lg font-medium">{formatDate(proposta.created_at)}</p>
        </Card>
        {proposta.prazo_validade && (
          <Card className="p-4">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <Clock className="w-4 h-4" />
              <span className="text-sm">Validade</span>
            </div>
            <p className="text-lg font-medium">{formatDate(proposta.prazo_validade)}</p>
          </Card>
        )}
      </div>

      {/* Info Grid */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Informações</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <Label className="text-muted-foreground text-xs">Imóvel</Label>
            <p><EntityLink type="imovel" id={proposta.imovel_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Cliente</Label>
            <p><EntityLink type="cliente" id={proposta.cliente_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Corretor</Label>
            <p><EntityLink type="cliente" id={proposta.corretor_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Atualizada em</Label>
            <p>{formatDate(proposta.updated_at)}</p>
          </div>
          {proposta.condicoes_pagamento && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Condições de Pagamento</Label>
              <p className="whitespace-pre-wrap">{proposta.condicoes_pagamento}</p>
            </div>
          )}
          {proposta.observacoes && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Observações</Label>
              <p className="whitespace-pre-wrap">{proposta.observacoes}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Edit Form */}
      {canChangeStatus && (
        <Card className="p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Editar Dados</h3>
            {!editando ? (
              <Button variant="outline" size="sm" onClick={() => setEditando(true)}>
                <Edit className="w-4 h-4 mr-2" />
                Editar
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={handleCancel}>
                  <X className="w-4 h-4 mr-2" />
                  Cancelar
                </Button>
                <Button size="sm" onClick={handleSubmit(onSubmit)} disabled={isPending}>
                  <Save className="w-4 h-4 mr-2" />
                  Salvar
                </Button>
              </div>
            )}
          </div>
          {editando && (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="valor_proposta">Valor (R$)</Label>
                  <Input id="valor_proposta" type="number" min={0} step={0.01} {...register('valor_proposta')} />
                  {errors.valor_proposta && <p className="text-sm text-destructive mt-1">{errors.valor_proposta.message}</p>}
                </div>
                <div>
                  <Label htmlFor="prazo_validade">Prazo de Validade</Label>
                  <Input id="prazo_validade" type="date" {...register('prazo_validade')} />
                </div>
                <div className="col-span-full">
                  <Label htmlFor="condicoes_pagamento">Condições de Pagamento</Label>
                  <Textarea id="condicoes_pagamento" {...register('condicoes_pagamento')} rows={2} />
                </div>
                <div className="col-span-full">
                  <Label htmlFor="observacoes">Observações</Label>
                  <Textarea id="observacoes" {...register('observacoes')} rows={2} />
                </div>
              </div>
            </form>
          )}
        </Card>
      )}

      {/* Status Actions */}
      {canChangeStatus && (
        <Card className="p-4 sm:p-6">
          <h3 className="text-lg font-semibold mb-3">Ações</h3>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="text-green-600 hover:text-green-700"
              onClick={() => handleStatusChange('aceita')}
            >
              <CheckCircle2 className="w-4 h-4 mr-2" />
              Aceitar Proposta
            </Button>
            <Button
              variant="outline"
              className="text-red-600 hover:text-red-700"
              onClick={() => handleStatusChange('recusada')}
            >
              <XCircle className="w-4 h-4 mr-2" />
              Recusar Proposta
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
