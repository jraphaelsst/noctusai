import { useState } from 'react';
import { Card } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { EntityLink } from '@/components/ui/entity-link';
import { useUpdateContrato } from '@/hooks/useContratos';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Contrato } from '@/types/contratos';
import { DollarSign, Calendar, CreditCard, FileText, Edit, Save, X } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const editSchema = z.object({
  valor_total: z.coerce.number().min(0),
  valor_entrada: z.coerce.number().min(0),
  num_parcelas: z.coerce.number().min(0),
  data_fim: z.string().optional(),
  observacoes: z.string().optional(),
});

type EditFormData = z.infer<typeof editSchema>;

interface ContratoResumoProps {
  contrato: Contrato;
}

export function ContratoResumo({ contrato }: ContratoResumoProps) {
  const [editando, setEditando] = useState(false);
  const { mutate: updateContrato, isPending } = useUpdateContrato();

  const canEdit = contrato.status === 'rascunho' || contrato.status === 'ativo';

  const { register, handleSubmit, formState: { errors }, reset } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      valor_total: contrato.valor_total,
      valor_entrada: contrato.valor_entrada,
      num_parcelas: contrato.num_parcelas,
      data_fim: contrato.data_fim || '',
      observacoes: contrato.observacoes || '',
    },
  });

  const onSubmit = (data: EditFormData) => {
    updateContrato(
      {
        id: contrato.id,
        valor_total: data.valor_total,
        valor_entrada: data.valor_entrada,
        num_parcelas: data.num_parcelas,
        data_fim: data.data_fim || undefined,
        observacoes: data.observacoes || undefined,
      },
      { onSuccess: () => setEditando(false) }
    );
  };

  const handleCancel = () => {
    reset();
    setEditando(false);
  };

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-sm">Valor Total</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(contrato.valor_total)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <CreditCard className="w-4 h-4" />
            <span className="text-sm">Entrada</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(contrato.valor_entrada || 0)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <FileText className="w-4 h-4" />
            <span className="text-sm">Parcelas</span>
          </div>
          <p className="text-2xl font-bold">{contrato.num_parcelas || 0}x</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Calendar className="w-4 h-4" />
            <span className="text-sm">Assinatura</span>
          </div>
          <p className="text-lg font-medium">
            {contrato.data_assinatura ? formatDate(contrato.data_assinatura) : 'Pendente'}
          </p>
        </Card>
      </div>

      {/* Info Grid */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Informações</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <Label className="text-muted-foreground text-xs">Cliente</Label>
            <p><EntityLink type="cliente" id={contrato.cliente_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Imóvel</Label>
            <p><EntityLink type="imovel" id={contrato.imovel_id} /></p>
          </div>
          {contrato.proposta_id && (
            <div>
              <Label className="text-muted-foreground text-xs">Proposta</Label>
              <p><EntityLink type="proposta" id={contrato.proposta_id} /></p>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground text-xs">Início</Label>
            <p>{formatDate(contrato.data_inicio)}</p>
          </div>
          {contrato.data_fim && (
            <div>
              <Label className="text-muted-foreground text-xs">Fim</Label>
              <p>{formatDate(contrato.data_fim)}</p>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground text-xs">Criado em</Label>
            <p>{formatDate(contrato.created_at)}</p>
          </div>
          {contrato.observacoes && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Observações</Label>
              <p className="whitespace-pre-wrap">{contrato.observacoes}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Edit Form */}
      {canEdit && (
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
                  <Label htmlFor="valor_total">Valor Total (R$)</Label>
                  <Input id="valor_total" type="number" min={0} step={0.01} {...register('valor_total')} />
                  {errors.valor_total && <p className="text-sm text-destructive mt-1">{errors.valor_total.message}</p>}
                </div>
                <div>
                  <Label htmlFor="valor_entrada">Entrada (R$)</Label>
                  <Input id="valor_entrada" type="number" min={0} step={0.01} {...register('valor_entrada')} />
                </div>
                <div>
                  <Label htmlFor="num_parcelas">Nº Parcelas</Label>
                  <Input id="num_parcelas" type="number" min={0} {...register('num_parcelas')} />
                </div>
                <div>
                  <Label htmlFor="data_fim">Data Fim</Label>
                  <Input id="data_fim" type="date" {...register('data_fim')} />
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
    </div>
  );
}
