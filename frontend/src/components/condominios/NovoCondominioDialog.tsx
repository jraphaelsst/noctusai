import { useForm } from 'react-hook-form';
import { useCreateCondominio, NovoCondominioForm } from '@/hooks/useCondominios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NovoCondominioDialog({ open, onOpenChange }: Props) {
  const createMutation = useCreateCondominio();
  const { register, handleSubmit, reset, setValue, watch } = useForm<NovoCondominioForm>({
    defaultValues: {
      nome: '',
      possui_portaria: false,
      possui_piscina: false,
      possui_academia: false,
      possui_salao_festas: false,
      possui_playground: false,
      possui_churrasqueira: false,
    },
  });

  const onSubmit = async (data: NovoCondominioForm) => {
    await createMutation.mutateAsync(data);
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Novo Condomínio</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Info básica */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Informações Básicas</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Label htmlFor="nome">Nome do Condomínio *</Label>
                <Input {...register('nome', { required: true })} placeholder="Ex: Residencial Park" />
              </div>
              <div>
                <Label htmlFor="endereco">Endereço</Label>
                <Input {...register('endereco')} placeholder="Rua, número" />
              </div>
              <div>
                <Label htmlFor="bairro">Bairro</Label>
                <Input {...register('bairro')} />
              </div>
              <div>
                <Label htmlFor="cidade">Cidade</Label>
                <Input {...register('cidade')} />
              </div>
              <div>
                <Label htmlFor="estado">Estado</Label>
                <Input {...register('estado')} placeholder="SP" />
              </div>
              <div>
                <Label htmlFor="cep">CEP</Label>
                <Input {...register('cep')} placeholder="00000-000" />
              </div>
              <div>
                <Label htmlFor="valor_condominio">Valor do Condomínio (R$/mês)</Label>
                <Input type="number" step="0.01" {...register('valor_condominio', { valueAsNumber: true })} />
              </div>
            </div>
          </div>

          {/* Estrutura */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Estrutura</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="torres">Torres</Label>
                <Input type="number" {...register('torres', { valueAsNumber: true })} />
              </div>
              <div>
                <Label htmlFor="unidades_por_andar">Unidades por Andar</Label>
                <Input type="number" {...register('unidades_por_andar', { valueAsNumber: true })} />
              </div>
              <div>
                <Label htmlFor="total_unidades">Total de Unidades</Label>
                <Input type="number" {...register('total_unidades', { valueAsNumber: true })} />
              </div>
            </div>
          </div>

          {/* Administração */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Administração</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="sindico">Síndico</Label>
                <Input {...register('sindico')} />
              </div>
              <div>
                <Label htmlFor="telefone_sindico">Telefone do Síndico</Label>
                <Input {...register('telefone_sindico')} />
              </div>
              <div>
                <Label htmlFor="administradora">Administradora</Label>
                <Input {...register('administradora')} />
              </div>
            </div>
          </div>

          {/* Infraestrutura */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Infraestrutura</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[
                { key: 'possui_portaria', label: 'Portaria 24h' },
                { key: 'possui_piscina', label: 'Piscina' },
                { key: 'possui_academia', label: 'Academia' },
                { key: 'possui_salao_festas', label: 'Salão de Festas' },
                { key: 'possui_playground', label: 'Playground' },
                { key: 'possui_churrasqueira', label: 'Churrasqueira' },
              ].map(({ key, label }) => (
                <div key={key} className="flex items-center space-x-2">
                  <Switch
                    checked={watch(key as any)}
                    onCheckedChange={(v) => setValue(key as any, v)}
                  />
                  <Label>{label}</Label>
                </div>
              ))}
            </div>
          </div>

          {/* Observações */}
          <div>
            <Label htmlFor="observacoes">Observações</Label>
            <Textarea {...register('observacoes')} rows={3} />
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
