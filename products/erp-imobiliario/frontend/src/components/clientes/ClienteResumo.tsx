import { useState } from 'react';
import { Card } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { useUpdateCliente } from '@/hooks/useClientes';
import { Cliente } from '@/types/clientes';
import { formatCurrency } from '@/lib/utils';
import { Edit, Save, X, Mail, Phone, TrendingUp, DollarSign, Globe, Star } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const ORIGENS = ['indicacao', 'site', 'facebook', 'instagram', 'google', 'portal', 'placa', 'plantao', 'outro'];

const editSchema = z.object({
  nome: z.string().min(2, 'Nome deve ter no mínimo 2 caracteres'),
  email: z.string().email('Email inválido').or(z.literal('')).optional(),
  telefone: z.string().optional(),
  origem: z.string().optional(),
  interesse: z.string().optional(),
  probabilidade: z.coerce.number().min(0).max(100),
  valor_estimado: z.coerce.number().min(0),
  observacoes: z.string().optional(),
});

type EditFormData = z.infer<typeof editSchema>;

interface ClienteResumoProps {
  cliente: Cliente;
}

export function ClienteResumo({ cliente }: ClienteResumoProps) {
  const [editando, setEditando] = useState(false);
  const { mutate: updateCliente, isPending } = useUpdateCliente();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    setValue,
    watch,
  } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      nome: cliente.nome,
      email: cliente.email || '',
      telefone: cliente.telefone || '',
      origem: cliente.origem || '',
      interesse: cliente.interesse || '',
      probabilidade: cliente.probabilidade,
      valor_estimado: cliente.valor_estimado,
      observacoes: cliente.observacoes || '',
    },
  });

  const origemValue = watch('origem');

  const onSubmit = (data: EditFormData) => {
    updateCliente(
      {
        id: cliente.id,
        nome: data.nome,
        email: data.email || undefined,
        telefone: data.telefone || undefined,
        origem: data.origem || undefined,
        interesse: data.interesse || undefined,
        probabilidade: data.probabilidade,
        valor_estimado: data.valor_estimado,
        observacoes: data.observacoes || undefined,
      },
      {
        onSuccess: () => {
          setEditando(false);
        },
      }
    );
  };

  const handleCancel = () => {
    reset({
      nome: cliente.nome,
      email: cliente.email || '',
      telefone: cliente.telefone || '',
      origem: cliente.origem || '',
      interesse: cliente.interesse || '',
      probabilidade: cliente.probabilidade,
      valor_estimado: cliente.valor_estimado,
      observacoes: cliente.observacoes || '',
    });
    setEditando(false);
  };

  return (
    <div className="space-y-4">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm">Probabilidade</span>
          </div>
          <p className="text-2xl font-bold">{cliente.probabilidade}%</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-sm">Valor Estimado</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(Number(cliente.valor_estimado))}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Globe className="w-4 h-4" />
            <span className="text-sm">Origem</span>
          </div>
          <p className="text-lg font-medium capitalize">{cliente.origem || '-'}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Star className="w-4 h-4" />
            <span className="text-sm">Interesse</span>
          </div>
          <p className="text-lg font-medium">{cliente.interesse || '-'}</p>
        </Card>
      </div>

      {/* Contact & details */}
      <Card className="p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Dados do Cliente</h3>
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

        {!editando ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Email</Label>
                <p>{cliente.email || '-'}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Phone className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Telefone</Label>
                <p>{cliente.telefone || '-'}</p>
              </div>
            </div>
            {cliente.observacoes && (
              <div className="col-span-full">
                <Label className="text-muted-foreground text-xs">Observações</Label>
                <p className="text-sm mt-1 whitespace-pre-wrap">{cliente.observacoes}</p>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="nome">Nome *</Label>
                <Input id="nome" {...register('nome')} />
                {errors.nome && <p className="text-sm text-destructive mt-1">{errors.nome.message}</p>}
              </div>
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" {...register('email')} />
                {errors.email && <p className="text-sm text-destructive mt-1">{errors.email.message}</p>}
              </div>
              <div>
                <Label htmlFor="telefone">Telefone</Label>
                <Input id="telefone" {...register('telefone')} />
              </div>
              <div>
                <Label htmlFor="origem">Origem</Label>
                <Select value={origemValue} onValueChange={(v) => setValue('origem', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {ORIGENS.map((o) => (
                      <SelectItem key={o} value={o}>
                        {o.charAt(0).toUpperCase() + o.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="interesse">Interesse</Label>
                <Input id="interesse" {...register('interesse')} />
              </div>
              <div>
                <Label htmlFor="probabilidade">Probabilidade (%)</Label>
                <Input id="probabilidade" type="number" min={0} max={100} {...register('probabilidade')} />
                {errors.probabilidade && <p className="text-sm text-destructive mt-1">{errors.probabilidade.message}</p>}
              </div>
              <div>
                <Label htmlFor="valor_estimado">Valor Estimado (R$)</Label>
                <Input id="valor_estimado" type="number" min={0} step={0.01} {...register('valor_estimado')} />
              </div>
              <div className="col-span-full">
                <Label htmlFor="observacoes">Observações</Label>
                <Textarea id="observacoes" {...register('observacoes')} rows={3} />
              </div>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
