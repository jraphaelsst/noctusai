import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useCliente, useUpdateCliente, useToggleArquivarCliente } from '@/hooks/useClientes';
import { useAtividades, useCreateAtividade } from '@/hooks/useAtividades';
import { LeadScoreBadge } from '@/components/clientes/LeadScoreBadge';
import { ArrowLeft, Edit, Archive, MessageSquare } from 'lucide-react';
import { ETAPAS_CONFIG, TIPOS_ATIVIDADE } from '@/lib/etapasConfig';
import { formatDate } from '@/lib/utils';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TipoAtividade } from '@/types/clientes';

const atividadeSchema = z.object({
  tipo: z.enum(['ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro']),
  descricao: z.string().min(3, 'Descrição deve ter no mínimo 3 caracteres'),
});

type AtividadeFormData = z.infer<typeof atividadeSchema>;

export default function ClienteDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [editando, setEditando] = useState(false);

  const { data: cliente, isLoading } = useCliente(id);
  const { data: atividades } = useAtividades(id);
  const { mutate: updateCliente } = useUpdateCliente();
  const { mutate: toggleArquivar } = useToggleArquivarCliente();
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

  const onSubmitAtividade = (data: AtividadeFormData) => {
    if (!id) return;
    
    createAtividade(
      {
        cliente_id: id,
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

  if (isLoading) {
    return (
      <div className="container mx-auto p-6">
        <div>Carregando...</div>
      </div>
    );
  }

  if (!cliente) {
    return (
      <div className="container mx-auto p-6">
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">Cliente não encontrado</p>
          <Button onClick={() => navigate('/clientes')} className="mt-4">
            Voltar para Clientes
          </Button>
        </Card>
      </div>
    );
  }

  const etapaConfig = ETAPAS_CONFIG[cliente.etapa_atual];

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <Button variant="ghost" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="w-4 h-4 mr-2" />
        Voltar
      </Button>

      <div className="grid gap-4 sm:gap-6">
        {/* Header */}
        <Card className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row items-start justify-between gap-4 mb-4">
            <div className="flex-1 min-w-0 w-full">
              <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
                <h1 className="text-2xl sm:text-3xl font-bold truncate">{cliente.nome}</h1>
                <Badge className={etapaConfig.bgColor}>{etapaConfig.label}</Badge>
                {cliente.arquivado && <Badge variant="secondary">Arquivado</Badge>}
                <LeadScoreBadge cliente={cliente} />
              </div>
              {cliente.usuario && (
                <p className="text-sm text-muted-foreground">
                  Responsável: {cliente.usuario.nome}
                </p>
              )}
            </div>

            <div className="flex flex-wrap gap-2 w-full sm:w-auto">
              <Button variant="outline" onClick={() => setEditando(!editando)} className="flex-1 sm:flex-none">
                <Edit className="w-4 h-4 mr-2" />
                {editando ? 'Cancelar' : 'Editar'}
              </Button>
              <Button
                variant="outline"
                onClick={() => toggleArquivar(cliente.id)}
                className="flex-1 sm:flex-none"
              >
                <Archive className="w-4 h-4 mr-2" />
                <span className="hidden sm:inline">{cliente.arquivado ? 'Desarquivar' : 'Arquivar'}</span>
                <span className="sm:hidden">{cliente.arquivado ? 'Restaurar' : 'Arquivar'}</span>
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <Label className="text-muted-foreground">Probabilidade</Label>
              <p className="text-lg font-semibold">{cliente.probabilidade}%</p>
            </div>
            <div>
              <Label className="text-muted-foreground">Valor Estimado</Label>
              <p className="text-lg font-semibold">
                {new Intl.NumberFormat('pt-BR', {
                  style: 'currency',
                  currency: 'BRL',
                }).format(Number(cliente.valor_estimado))}
              </p>
            </div>
            {cliente.origem && (
              <div>
                <Label className="text-muted-foreground">Origem</Label>
                <p className="text-lg">{cliente.origem}</p>
              </div>
            )}
            {cliente.interesse && (
              <div>
                <Label className="text-muted-foreground">Interesse</Label>
                <p className="text-lg">{cliente.interesse}</p>
              </div>
            )}
          </div>
        </Card>

        {/* Dados do Cliente */}
        <Card className="p-4 sm:p-6">
          <h2 className="text-xl font-semibold mb-4">Dados do Cliente</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label>Email</Label>
              <p className="mt-1">{cliente.email || '-'}</p>
            </div>
            <div>
              <Label>Telefone</Label>
              <p className="mt-1">{cliente.telefone || '-'}</p>
            </div>
            {cliente.observacoes && (
              <div className="col-span-2">
                <Label>Observações</Label>
                <p className="mt-1 text-sm">{cliente.observacoes}</p>
              </div>
            )}
          </div>
        </Card>

        {/* Timeline de Atividades */}
        <Card className="p-6">
          <h2 className="text-xl font-semibold mb-4">Timeline de Atividades</h2>

          {/* Form para adicionar atividade */}
          <form onSubmit={handleSubmit(onSubmitAtividade)} className="mb-6 pb-6 border-b">
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

          {/* Lista de atividades */}
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
      </div>
    </div>
  );
}
