import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useCreatePerfilPermuta } from '@/hooks/usePermutas';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';

interface NovoPerfilPermutaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NovoPerfilPermutaDialog({ open, onOpenChange }: NovoPerfilPermutaDialogProps) {
  const createMutation = useCreatePerfilPermuta();
  const [regioes, setRegioes] = useState<string[]>([]);
  const [novaRegiao, setNovaRegiao] = useState('');

  const { register, handleSubmit, formState: { errors }, setValue, watch, reset } = useForm({
    defaultValues: {
      natureza: '' as 'permuta_imovel' | 'permuta_automovel',
      aceita_completar_diferenca: false,
      regiao_preferida: [] as string[],
      valor: 0,
      status: 'ativo',
    },
  });

  const watchedNatureza = watch('natureza');
  const watchedAceitaCompletar = watch('aceita_completar_diferenca');

  const adicionarRegiao = () => {
    if (novaRegiao) {
      const novasRegioes = [...regioes, novaRegiao];
      setRegioes(novasRegioes);
      setValue('regiao_preferida', novasRegioes);
      setNovaRegiao('');
    }
  };

  const removerRegiao = (index: number) => {
    const novasRegioes = regioes.filter((_, i) => i !== index);
    setRegioes(novasRegioes);
    setValue('regiao_preferida', novasRegioes);
  };

  const onSubmit = async (data: any) => {
    const formData: any = {
      ...data,
      regiao_preferida: regioes,
    };

    await createMutation.mutateAsync(formData);
    reset();
    setRegioes([]);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Criar Perfil de Permuta</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Natureza (discriminator) */}
          <div>
            <Label htmlFor="natureza">Tipo de Permuta *</Label>
            <Select onValueChange={(v) => setValue('natureza', v as any)}>
              <SelectTrigger>
                <SelectValue placeholder="O que você oferece em troca?" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="permuta_imovel">Imóvel</SelectItem>
                <SelectItem value="permuta_automovel">Automóvel</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Campos para Permuta Imóvel */}
          {watchedNatureza === 'permuta_imovel' && (
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Dados do Imóvel Oferecido</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Tipo de Imóvel</Label>
                  <Select onValueChange={(v) => setValue('tipo_imovel', v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="casa">Casa</SelectItem>
                      <SelectItem value="apartamento">Apartamento</SelectItem>
                      <SelectItem value="terreno">Terreno</SelectItem>
                      <SelectItem value="comercial">Comercial</SelectItem>
                      <SelectItem value="rural">Rural</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Zona</Label>
                  <Select onValueChange={(v) => setValue('zona', v)}>
                    <SelectTrigger><SelectValue placeholder="Zona" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="norte">Norte</SelectItem>
                      <SelectItem value="sul">Sul</SelectItem>
                      <SelectItem value="leste">Leste</SelectItem>
                      <SelectItem value="oeste">Oeste</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Condomínio</Label>
                  <Input {...register('condominio_nome')} placeholder="Nome do condomínio" />
                </div>
                <div>
                  <Label>CEP</Label>
                  <Input {...register('cep')} placeholder="00000-000" />
                </div>
                <div>
                  <Label>Cidade</Label>
                  <Input {...register('cidade')} />
                </div>
                <div>
                  <Label>Estado</Label>
                  <Input {...register('estado')} placeholder="SP" />
                </div>
                <div>
                  <Label>Bairro</Label>
                  <Input {...register('bairro')} />
                </div>
                <div>
                  <Label>Valor (R$)</Label>
                  <Input type="number" step="0.01" {...register('valor', { valueAsNumber: true })} />
                </div>
                <div>
                  <Label>Quartos</Label>
                  <Input type="number" {...register('quartos', { valueAsNumber: true })} />
                </div>
                <div>
                  <Label>Vagas</Label>
                  <Input type="number" {...register('vagas', { valueAsNumber: true })} />
                </div>
              </div>

              <div>
                <Label>Regiões Preferidas</Label>
                <div className="flex gap-2 mb-2">
                  <Input value={novaRegiao} onChange={(e) => setNovaRegiao(e.target.value)} placeholder="Cidade, estado ou bairro" />
                  <Button type="button" variant="outline" onClick={adicionarRegiao}>Adicionar</Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {regioes.map((r, i) => (
                    <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => removerRegiao(i)}>{r} ×</Badge>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Campos para Permuta Automóvel */}
          {watchedNatureza === 'permuta_automovel' && (
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Dados do Veículo Oferecido</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Tipo de Veículo</Label>
                  <Select onValueChange={(v) => setValue('tipo_veiculo', v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="carro">Carro</SelectItem>
                      <SelectItem value="moto">Moto</SelectItem>
                      <SelectItem value="suv">SUV</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Marca</Label>
                  <Input {...register('marca')} placeholder="Ex: Honda" />
                </div>
                <div>
                  <Label>Modelo</Label>
                  <Input {...register('modelo')} placeholder="Ex: Civic" />
                </div>
                <div>
                  <Label>Motor</Label>
                  <Select onValueChange={(v) => setValue('motor', v)}>
                    <SelectTrigger><SelectValue placeholder="Combustível" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="gasolina">Gasolina</SelectItem>
                      <SelectItem value="alcool">Álcool</SelectItem>
                      <SelectItem value="flex">Flex</SelectItem>
                      <SelectItem value="eletrico">Elétrico</SelectItem>
                      <SelectItem value="hibrido">Híbrido</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Ano</Label>
                  <Input type="number" {...register('ano', { valueAsNumber: true })} />
                </div>
                <div>
                  <Label>Quilometragem</Label>
                  <Input type="number" {...register('quilometragem', { valueAsNumber: true })} />
                </div>
                <div>
                  <Label>Valor (R$)</Label>
                  <Input type="number" step="0.01" {...register('valor', { valueAsNumber: true })} />
                </div>
              </div>
            </div>
          )}

          {/* Flexibilidade */}
          {watchedNatureza && (
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Flexibilidade</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Faixa de Preço Mínima</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_min', { valueAsNumber: true })} />
                </div>
                <div>
                  <Label>Faixa de Preço Máxima</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_max', { valueAsNumber: true })} />
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <Switch
                  checked={watchedAceitaCompletar}
                  onCheckedChange={(v) => setValue('aceita_completar_diferenca', v)}
                />
                <Label>Aceita completar diferença de valores</Label>
              </div>

              {watchedAceitaCompletar && (
                <div>
                  <Label>Limite de Complemento</Label>
                  <Input type="number" step="0.01" {...register('limite_complemento', { valueAsNumber: true })} />
                </div>
              )}

              <div>
                <Label>Observações</Label>
                <Textarea {...register('observacoes')} rows={3} />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" disabled={createMutation.isPending || !watchedNatureza}>
              {createMutation.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
