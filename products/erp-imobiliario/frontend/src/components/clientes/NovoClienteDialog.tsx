import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@noctusai/seed/components/ui/dialog';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useCreateCliente } from '@/hooks/useClientes';

const clienteSchema = z.object({
  nome: z.string().min(3, 'Nome deve ter no mínimo 3 caracteres'),
  email: z.string().email('Email inválido').optional().or(z.literal('')),
  telefone: z.string().min(10, 'Telefone deve ter no mínimo 10 dígitos').optional().or(z.literal('')),
  origem: z.string().optional(),
  interesse: z.string().optional(),
  observacoes: z.string().optional(),
  probabilidade: z.coerce.number().min(0).max(100).default(10),
  valor_estimado: z.coerce.number().min(0).default(0),
});

type ClienteFormData = z.infer<typeof clienteSchema>;

interface NovoClienteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NovoClienteDialog({ open, onOpenChange }: NovoClienteDialogProps) {
  const { mutate: criarCliente, isPending } = useCreateCliente();
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    setValue,
    watch,
  } = useForm<ClienteFormData>({
    resolver: zodResolver(clienteSchema),
    defaultValues: {
      probabilidade: 10,
      valor_estimado: 0,
    },
  });

  const origemValue = watch('origem');

  const onSubmit = (data: ClienteFormData) => {
    const clienteData = {
      nome: data.nome,
      email: data.email || undefined,
      telefone: data.telefone || undefined,
      origem: data.origem,
      interesse: data.interesse,
      observacoes: data.observacoes,
      probabilidade: data.probabilidade,
      valor_estimado: data.valor_estimado,
    };

    criarCliente(clienteData, {
      onSuccess: () => {
        reset();
        onOpenChange(false);
      },
    });
  };

  const origens = ['Indicação', 'Site', 'Redes Sociais', 'Telefone', 'Email', 'Evento', 'Outros'];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Novo Cliente</DialogTitle>
          <DialogDescription>
            Preencha os dados do novo cliente. Ele será adicionado à etapa de Qualificação.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label htmlFor="nome">Nome *</Label>
              <Input id="nome" {...register('nome')} />
              {errors.nome && (
                <p className="text-sm text-destructive mt-1">{errors.nome.message}</p>
              )}
            </div>

            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...register('email')} />
              {errors.email && (
                <p className="text-sm text-destructive mt-1">{errors.email.message}</p>
              )}
            </div>

            <div>
              <Label htmlFor="telefone">Telefone</Label>
              <Input id="telefone" {...register('telefone')} />
              {errors.telefone && (
                <p className="text-sm text-destructive mt-1">{errors.telefone.message}</p>
              )}
            </div>

            <div>
              <Label htmlFor="origem">Origem</Label>
              <Select value={origemValue} onValueChange={(value) => setValue('origem', value)}>
                <SelectTrigger id="origem">
                  <SelectValue placeholder="Selecione..." />
                </SelectTrigger>
                <SelectContent>
                  {origens.map((origem) => (
                    <SelectItem key={origem} value={origem}>
                      {origem}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="interesse">Interesse</Label>
              <Input id="interesse" {...register('interesse')} placeholder="Ex: Apartamento 2 quartos" />
            </div>

            <div>
              <Label htmlFor="probabilidade">Probabilidade (%)</Label>
              <Input id="probabilidade" type="number" min="0" max="100" {...register('probabilidade')} />
              {errors.probabilidade && (
                <p className="text-sm text-destructive mt-1">{errors.probabilidade.message}</p>
              )}
            </div>

            <div>
              <Label htmlFor="valor_estimado">Valor Estimado (R$)</Label>
              <Input
                id="valor_estimado"
                type="number"
                min="0"
                step="0.01"
                {...register('valor_estimado')}
              />
              {errors.valor_estimado && (
                <p className="text-sm text-destructive mt-1">{errors.valor_estimado.message}</p>
              )}
            </div>

            <div className="col-span-2">
              <Label htmlFor="observacoes">Observações</Label>
              <Textarea id="observacoes" {...register('observacoes')} rows={3} />
            </div>
          </div>

          <div className="flex gap-2 justify-end">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Salvando...' : 'Criar Cliente'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
