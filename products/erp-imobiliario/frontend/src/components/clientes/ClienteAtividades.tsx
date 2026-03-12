import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAtividades, useCreateAtividade } from '@/hooks/useAtividades';
import { TIPOS_ATIVIDADE } from '@/lib/etapasConfig';
import { formatDate } from '@/lib/utils';
import { TipoAtividade } from '@/types/clientes';
import { MessageSquare } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const atividadeSchema = z.object({
  tipo: z.enum(['ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro']),
  descricao: z.string().min(3, 'Descrição deve ter no mínimo 3 caracteres'),
});

type AtividadeFormData = z.infer<typeof atividadeSchema>;

interface ClienteAtividadesProps {
  clienteId: string;
}

export function ClienteAtividades({ clienteId }: ClienteAtividadesProps) {
  const { data: atividades } = useAtividades(clienteId);
  const { mutate: createAtividade, isPending: criandoAtividade } = useCreateAtividade();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    setValue,
    watch,
  } = useForm<AtividadeFormData>({
    resolver: zodResolver(atividadeSchema),
    defaultValues: {
      tipo: 'ligacao',
    },
  });

  const tipoValue = watch('tipo');

  const onSubmit = (data: AtividadeFormData) => {
    createAtividade(
      {
        cliente_id: clienteId,
        tipo: data.tipo as TipoAtividade,
        descricao: data.descricao,
      },
      {
        onSuccess: () => {
          reset();
        },
      }
    );
  };

  return (
    <Card className="p-4 sm:p-6">
      <h3 className="text-lg font-semibold mb-4">Registrar Atividade</h3>

      <form onSubmit={handleSubmit(onSubmit)} className="mb-6 pb-6 border-b">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <Label htmlFor="tipo">Tipo</Label>
            <Select value={tipoValue} onValueChange={(value) => setValue('tipo', value as TipoAtividade)}>
              <SelectTrigger id="tipo">
                <SelectValue placeholder="Selecione o tipo" />
              </SelectTrigger>
              <SelectContent>
                {TIPOS_ATIVIDADE.map((tipo) => (
                  <SelectItem key={tipo.value} value={tipo.value}>
                    {tipo.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2">
            <Label htmlFor="descricao">Descrição *</Label>
            <div className="flex gap-2">
              <Input
                id="descricao"
                {...register('descricao')}
                placeholder="Descreva a atividade..."
              />
              <Button type="submit" disabled={criandoAtividade}>
                <MessageSquare className="w-4 h-4 mr-2" />
                Adicionar
              </Button>
            </div>
            {errors.descricao && (
              <p className="text-sm text-destructive mt-1">{errors.descricao.message}</p>
            )}
          </div>
        </div>
      </form>

      <div className="space-y-4">
        {atividades && atividades.length > 0 ? (
          atividades.map((atividade) => {
            const tipoAtividade = TIPOS_ATIVIDADE.find((t) => t.value === atividade.tipo);
            return (
              <div key={atividade.id} className="flex gap-4 pb-4 border-b last:border-0">
                <div className="w-24 flex-shrink-0">
                  <p className="text-sm font-medium">
                    {formatDate(atividade.data_execucao)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(atividade.data_execucao, true).split(' às ')[1]}
                  </p>
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="outline">{tipoAtividade?.label}</Badge>
                    {atividade.usuario && (
                      <span className="text-sm text-muted-foreground">
                        por {atividade.usuario.nome}
                      </span>
                    )}
                  </div>
                  <p className="text-sm">{atividade.descricao}</p>
                </div>
              </div>
            );
          })
        ) : (
          <p className="text-center text-muted-foreground py-8">
            Nenhuma atividade registrada
          </p>
        )}
      </div>
    </Card>
  );
}
