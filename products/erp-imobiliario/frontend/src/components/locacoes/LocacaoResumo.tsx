import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { EntityLink } from '@/components/ui/entity-link';
import { useUpdateLocacao } from '@/hooks/useLocacoes';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { ContratoLocacao, IndiceReajuste } from '@/types/locacoes';
import { DollarSign, Calendar, Percent, Shield, Edit, Save, X } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const INDICES: IndiceReajuste[] = ['IGPM', 'IPCA', 'INPC', 'fixo'];

const editSchema = z.object({
  valor_aluguel: z.coerce.number().min(0),
  dia_vencimento: z.coerce.number().min(1).max(31),
  taxa_administracao: z.coerce.number().min(0).max(100),
  valor_caucao: z.coerce.number().min(0).optional(),
  data_fim: z.string().optional(),
  indice_reajuste: z.string().optional(),
  observacoes: z.string().optional(),
});

type EditFormData = z.infer<typeof editSchema>;

interface LocacaoResumoProps {
  locacao: ContratoLocacao;
}

export function LocacaoResumo({ locacao }: LocacaoResumoProps) {
  const [editando, setEditando] = useState(false);
  const { mutate: updateLocacao, isPending } = useUpdateLocacao();

  const canEdit = locacao.status === 'ativo';

  const { register, handleSubmit, formState: { errors }, reset, setValue, watch } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      valor_aluguel: locacao.valor_aluguel,
      dia_vencimento: locacao.dia_vencimento,
      taxa_administracao: locacao.taxa_administracao,
      valor_caucao: locacao.valor_caucao || 0,
      data_fim: locacao.data_fim || '',
      indice_reajuste: locacao.indice_reajuste,
      observacoes: locacao.observacoes || '',
    },
  });

  const indiceValue = watch('indice_reajuste');

  const onSubmit = (data: EditFormData) => {
    updateLocacao(
      {
        id: locacao.id,
        valor_aluguel: data.valor_aluguel,
        dia_vencimento: data.dia_vencimento,
        taxa_administracao: data.taxa_administracao,
        valor_caucao: data.valor_caucao || undefined,
        data_fim: data.data_fim || undefined,
        indice_reajuste: (data.indice_reajuste as IndiceReajuste) || undefined,
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
            <span className="text-sm">Aluguel</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(locacao.valor_aluguel)}/mês</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Calendar className="w-4 h-4" />
            <span className="text-sm">Vencimento</span>
          </div>
          <p className="text-2xl font-bold">Dia {locacao.dia_vencimento}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Percent className="w-4 h-4" />
            <span className="text-sm">Taxa Adm.</span>
          </div>
          <p className="text-2xl font-bold">{locacao.taxa_administracao}%</p>
        </Card>
        {locacao.valor_caucao != null && locacao.valor_caucao > 0 && (
          <Card className="p-4">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <Shield className="w-4 h-4" />
              <span className="text-sm">Caução</span>
            </div>
            <p className="text-2xl font-bold">{formatCurrency(locacao.valor_caucao)}</p>
          </Card>
        )}
      </div>

      {/* Info Grid */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Informações</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <Label className="text-muted-foreground text-xs">Imóvel</Label>
            <p><EntityLink type="imovel" id={locacao.imovel_id} /></p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Locatário</Label>
            <p><EntityLink type="cliente" id={locacao.locatario_id} /></p>
          </div>
          {locacao.proprietario_id && (
            <div>
              <Label className="text-muted-foreground text-xs">Proprietário</Label>
              <p><EntityLink type="cliente" id={locacao.proprietario_id} /></p>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground text-xs">Período</Label>
            <p>{formatDate(locacao.data_inicio)} — {formatDate(locacao.data_fim)}</p>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Índice de Reajuste</Label>
            <p>{locacao.indice_reajuste}</p>
          </div>
          {locacao.percentual_reajuste != null && (
            <div>
              <Label className="text-muted-foreground text-xs">Percentual Reajuste</Label>
              <p>{locacao.percentual_reajuste}%</p>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground text-xs">Criado em</Label>
            <p>{formatDate(locacao.created_at)}</p>
          </div>
          {locacao.observacoes && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Observações</Label>
              <p className="whitespace-pre-wrap">{locacao.observacoes}</p>
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
                  <Label htmlFor="valor_aluguel">Aluguel (R$)</Label>
                  <Input id="valor_aluguel" type="number" min={0} step={0.01} {...register('valor_aluguel')} />
                  {errors.valor_aluguel && <p className="text-sm text-destructive mt-1">{errors.valor_aluguel.message}</p>}
                </div>
                <div>
                  <Label htmlFor="dia_vencimento">Dia Vencimento</Label>
                  <Input id="dia_vencimento" type="number" min={1} max={31} {...register('dia_vencimento')} />
                </div>
                <div>
                  <Label htmlFor="taxa_administracao">Taxa Adm. (%)</Label>
                  <Input id="taxa_administracao" type="number" min={0} max={100} step={0.1} {...register('taxa_administracao')} />
                </div>
                <div>
                  <Label htmlFor="valor_caucao">Caução (R$)</Label>
                  <Input id="valor_caucao" type="number" min={0} step={0.01} {...register('valor_caucao')} />
                </div>
                <div>
                  <Label htmlFor="data_fim">Data Fim</Label>
                  <Input id="data_fim" type="date" {...register('data_fim')} />
                </div>
                <div>
                  <Label>Índice de Reajuste</Label>
                  <Select value={indiceValue} onValueChange={(v) => setValue('indice_reajuste', v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {INDICES.map((idx) => (
                        <SelectItem key={idx} value={idx}>{idx}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
