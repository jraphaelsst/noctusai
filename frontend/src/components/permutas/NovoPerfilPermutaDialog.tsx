import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { perfilPermutaSchema, PerfilPermutaFormData } from '@/lib/imovelValidations';
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

  const { register, handleSubmit, formState: { errors }, setValue, watch, reset } = useForm<PerfilPermutaFormData>({
    resolver: zodResolver(perfilPermutaSchema),
    defaultValues: {
      aceita_completar_diferenca: false,
      regiao_preferida: [],
    },
  });

  const watchedCategoria = watch('categoria');
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

  const onSubmit = async (data: PerfilPermutaFormData) => {
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
          {/* Categoria */}
          <div>
            <Label htmlFor="categoria">Categoria *</Label>
            <Select onValueChange={(v) => setValue('categoria', v as any)}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione o tipo de bem" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="imovel">Imóvel</SelectItem>
                <SelectItem value="movel">Móvel (Carro/Moto)</SelectItem>
              </SelectContent>
            </Select>
            {errors.categoria && <p className="text-sm text-destructive">{errors.categoria.message}</p>}
          </div>

          {/* Campos para Imóvel */}
          {watchedCategoria === 'imovel' && (
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Detalhes do Imóvel Desejado</h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="tipo_imovel">Tipo de Imóvel</Label>
                  <Select onValueChange={(v) => setValue('tipo_imovel', v as any)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="casa">Casa</SelectItem>
                      <SelectItem value="apartamento">Apartamento</SelectItem>
                      <SelectItem value="terreno">Terreno</SelectItem>
                      <SelectItem value="comercial">Comercial</SelectItem>
                      <SelectItem value="rural">Rural</SelectItem>
                      <SelectItem value="outro">Outro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="quartos_min">Quartos Mínimos</Label>
                  <Input type="number" {...register('quartos_min')} />
                </div>

                <div>
                  <Label htmlFor="vagas_min">Vagas Mínimas</Label>
                  <Input type="number" {...register('vagas_min')} />
                </div>

                <div>
                  <Label htmlFor="metragem_min">Metragem Mínima (m²)</Label>
                  <Input type="number" {...register('metragem_min')} />
                </div>

                <div>
                  <Label htmlFor="metragem_max">Metragem Máxima (m²)</Label>
                  <Input type="number" {...register('metragem_max')} />
                </div>

                <div>
                  <Label htmlFor="faixa_preco_min">Preço Mínimo</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_min')} />
                </div>

                <div>
                  <Label htmlFor="faixa_preco_max">Preço Máximo</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_max')} />
                  {errors.faixa_preco_max && <p className="text-sm text-destructive">{errors.faixa_preco_max.message}</p>}
                </div>
              </div>

              <div>
                <Label>Regiões Preferidas</Label>
                <div className="flex gap-2 mb-2">
                  <Input
                    value={novaRegiao}
                    onChange={(e) => setNovaRegiao(e.target.value)}
                    placeholder="Digite cidade, estado ou bairro"
                  />
                  <Button type="button" variant="outline" onClick={adicionarRegiao}>
                    Adicionar
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {regioes.map((regiao, i) => (
                    <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => removerRegiao(i)}>
                      {regiao} ×
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Campos para Móvel */}
          {watchedCategoria === 'movel' && (
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Detalhes do Veículo Desejado</h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="tipo_movel">Tipo de Veículo</Label>
                  <Select onValueChange={(v) => setValue('tipo_movel', v as any)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="carro">Carro</SelectItem>
                      <SelectItem value="moto">Moto</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="marca">Marca</Label>
                  <Input {...register('marca')} />
                </div>

                <div>
                  <Label htmlFor="modelo">Modelo</Label>
                  <Input {...register('modelo')} />
                </div>

                <div>
                  <Label htmlFor="ano_min">Ano Mínimo</Label>
                  <Input type="number" {...register('ano_min')} />
                </div>

                <div>
                  <Label htmlFor="ano_max">Ano Máximo</Label>
                  <Input type="number" {...register('ano_max')} />
                </div>

                <div>
                  <Label htmlFor="quilometragem_max">KM Máxima</Label>
                  <Input type="number" {...register('quilometragem_max')} />
                </div>

                <div>
                  <Label htmlFor="faixa_preco_min">Preço Mínimo</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_min')} />
                </div>

                <div>
                  <Label htmlFor="faixa_preco_max">Preço Máximo</Label>
                  <Input type="number" step="0.01" {...register('faixa_preco_max')} />
                </div>
              </div>
            </div>
          )}

          {/* Flexibilidade */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Flexibilidade</h3>
            
            <div>
              <Label htmlFor="valor_estimado">Valor Estimado do Bem Oferecido</Label>
              <Input type="number" step="0.01" {...register('valor_estimado')} />
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
                <Label htmlFor="limite_complemento">Limite de Complemento</Label>
                <Input type="number" step="0.01" {...register('limite_complemento')} />
              </div>
            )}

            <div>
              <Label htmlFor="observacoes">Observações</Label>
              <Textarea {...register('observacoes')} rows={3} />
            </div>
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
