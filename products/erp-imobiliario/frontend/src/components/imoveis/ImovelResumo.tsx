import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Imovel, useUpdateImovel } from '@/hooks/useImoveis';
import { formatCurrency } from '@/lib/utils';
import {
  Edit, Save, X, DollarSign, Home, Maximize, BedDouble,
  Bath, Car, Building2, MapPin, Calendar, Shield, Tag,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const TIPOS = ['casa', 'apartamento', 'terreno', 'comercial', 'rural'];
const FINALIDADES = ['venda', 'aluguel', 'venda_aluguel'];

const editSchema = z.object({
  valor: z.coerce.number().min(0),
  tipo_imovel: z.string().optional(),
  finalidade: z.string().optional(),
  titulo_anuncio: z.string().optional(),
  descricao_seo: z.string().optional(),
  observacoes: z.string().optional(),
});

type EditFormData = z.infer<typeof editSchema>;

interface ImovelResumoProps {
  imovel: Imovel;
}

export function ImovelResumo({ imovel }: ImovelResumoProps) {
  const [editando, setEditando] = useState(false);
  const { mutate: updateImovel, isPending } = useUpdateImovel();

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
      valor: imovel.valor,
      tipo_imovel: imovel.tipo_imovel || '',
      finalidade: imovel.finalidade || '',
      titulo_anuncio: imovel.titulo_anuncio || '',
      descricao_seo: imovel.descricao_seo || '',
      observacoes: imovel.observacoes || '',
    },
  });

  const tipoValue = watch('tipo_imovel');
  const finalidadeValue = watch('finalidade');

  const onSubmit = (data: EditFormData) => {
    updateImovel(
      {
        id: imovel.id,
        valor: data.valor,
        tipo_imovel: data.tipo_imovel || undefined,
        finalidade: data.finalidade || undefined,
        titulo_anuncio: data.titulo_anuncio || undefined,
        descricao_seo: data.descricao_seo || undefined,
        observacoes: data.observacoes || undefined,
      },
      { onSuccess: () => setEditando(false) }
    );
  };

  const handleCancel = () => {
    reset({
      valor: imovel.valor,
      tipo_imovel: imovel.tipo_imovel || '',
      finalidade: imovel.finalidade || '',
      titulo_anuncio: imovel.titulo_anuncio || '',
      descricao_seo: imovel.descricao_seo || '',
      observacoes: imovel.observacoes || '',
    });
    setEditando(false);
  };

  const address = [
    [imovel.logradouro, imovel.numero].filter(Boolean).join(', '),
    imovel.complemento,
  ].filter(Boolean).join(' - ');

  return (
    <div className="space-y-4">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-sm">Valor</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(imovel.valor)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Home className="w-4 h-4" />
            <span className="text-sm">Tipo</span>
          </div>
          <p className="text-lg font-medium capitalize">{imovel.tipo_imovel || '-'}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Tag className="w-4 h-4" />
            <span className="text-sm">Finalidade</span>
          </div>
          <p className="text-lg font-medium capitalize">{imovel.finalidade || '-'}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Shield className="w-4 h-4" />
            <span className="text-sm">Status</span>
          </div>
          <p className="text-lg font-medium capitalize">{imovel.status || '-'}</p>
        </Card>
      </div>

      {/* Location */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <MapPin className="w-5 h-5" /> Localização
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          {address && (
            <div>
              <Label className="text-muted-foreground text-xs">Endereço</Label>
              <p>{address}</p>
            </div>
          )}
          {imovel.bairro && (
            <div>
              <Label className="text-muted-foreground text-xs">Bairro</Label>
              <p>{imovel.bairro}</p>
            </div>
          )}
          {(imovel.cidade || imovel.estado) && (
            <div>
              <Label className="text-muted-foreground text-xs">Cidade / Estado</Label>
              <p>{[imovel.cidade, imovel.estado].filter(Boolean).join(' / ')}</p>
            </div>
          )}
          {imovel.cep && (
            <div>
              <Label className="text-muted-foreground text-xs">CEP</Label>
              <p>{imovel.cep}</p>
            </div>
          )}
          {imovel.condominio_nome && (
            <div>
              <Label className="text-muted-foreground text-xs">Condomínio</Label>
              <p>{imovel.condominio_nome}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Specs */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Especificações</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          {imovel.quartos != null && (
            <div className="flex items-center gap-2">
              <BedDouble className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Quartos</Label>
                <p className="font-medium">{imovel.quartos}</p>
              </div>
            </div>
          )}
          {imovel.suites != null && (
            <div className="flex items-center gap-2">
              <BedDouble className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Suítes</Label>
                <p className="font-medium">{imovel.suites}</p>
              </div>
            </div>
          )}
          {imovel.banheiros != null && (
            <div className="flex items-center gap-2">
              <Bath className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Banheiros</Label>
                <p className="font-medium">{imovel.banheiros}</p>
              </div>
            </div>
          )}
          {imovel.vagas != null && (
            <div className="flex items-center gap-2">
              <Car className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Vagas</Label>
                <p className="font-medium">{imovel.vagas}</p>
              </div>
            </div>
          )}
          {imovel.area_privativa != null && (
            <div className="flex items-center gap-2">
              <Maximize className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Área Privativa</Label>
                <p className="font-medium">{imovel.area_privativa} m²</p>
              </div>
            </div>
          )}
          {imovel.area_total != null && (
            <div className="flex items-center gap-2">
              <Maximize className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Área Total</Label>
                <p className="font-medium">{imovel.area_total} m²</p>
              </div>
            </div>
          )}
          {imovel.andar != null && (
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Andar</Label>
                <p className="font-medium">{imovel.andar}°</p>
              </div>
            </div>
          )}
          {imovel.ano_construcao != null && (
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              <div>
                <Label className="text-muted-foreground text-xs">Ano Construção</Label>
                <p className="font-medium">{imovel.ano_construcao}</p>
              </div>
            </div>
          )}
          {imovel.iptu != null && (
            <div>
              <Label className="text-muted-foreground text-xs">IPTU</Label>
              <p className="font-medium">{formatCurrency(imovel.iptu)}</p>
            </div>
          )}
        </div>
      </Card>

      {/* SEO / Anúncio */}
      {(imovel.titulo_anuncio || imovel.descricao_seo || (imovel.palavras_chave && imovel.palavras_chave.length > 0) || (imovel.pontos_de_interesse && imovel.pontos_de_interesse.length > 0)) && (
        <Card className="p-4 sm:p-6">
          <h3 className="text-lg font-semibold mb-3">Anúncio & SEO</h3>
          <div className="space-y-3 text-sm">
            {imovel.titulo_anuncio && (
              <div>
                <Label className="text-muted-foreground text-xs">Título do Anúncio</Label>
                <p className="font-medium">{imovel.titulo_anuncio}</p>
              </div>
            )}
            {imovel.descricao_seo && (
              <div>
                <Label className="text-muted-foreground text-xs">Descrição SEO</Label>
                <p className="whitespace-pre-wrap">{imovel.descricao_seo}</p>
              </div>
            )}
            {imovel.palavras_chave && imovel.palavras_chave.length > 0 && (
              <div>
                <Label className="text-muted-foreground text-xs">Palavras-chave</Label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {imovel.palavras_chave.map((kw, i) => (
                    <Badge key={i} variant="secondary">{kw}</Badge>
                  ))}
                </div>
              </div>
            )}
            {imovel.pontos_de_interesse && imovel.pontos_de_interesse.length > 0 && (
              <div>
                <Label className="text-muted-foreground text-xs">Pontos de Interesse</Label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {imovel.pontos_de_interesse.map((pi, i) => (
                    <Badge key={i} variant="outline">{pi}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 mt-3">
            {imovel.pronto_para_portais && (
              <Badge className="bg-green-100 text-green-800">Pronto para Portais</Badge>
            )}
            {imovel.lqs_score_hint && (
              <span className="text-xs text-muted-foreground">LQS: {imovel.lqs_score_hint}</span>
            )}
          </div>
        </Card>
      )}

      {/* Edit form */}
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
                <Label htmlFor="valor">Valor (R$)</Label>
                <Input id="valor" type="number" min={0} step={0.01} {...register('valor')} />
                {errors.valor && <p className="text-sm text-destructive mt-1">{errors.valor.message}</p>}
              </div>
              <div>
                <Label htmlFor="tipo_imovel">Tipo</Label>
                <Select value={tipoValue} onValueChange={(v) => setValue('tipo_imovel', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {TIPOS.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="finalidade">Finalidade</Label>
                <Select value={finalidadeValue} onValueChange={(v) => setValue('finalidade', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="venda">Venda</SelectItem>
                    <SelectItem value="aluguel">Aluguel</SelectItem>
                    <SelectItem value="venda_aluguel">Venda e Aluguel</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="titulo_anuncio">Título do Anúncio</Label>
                <Input id="titulo_anuncio" {...register('titulo_anuncio')} />
              </div>
              <div className="col-span-full">
                <Label htmlFor="descricao_seo">Descrição SEO</Label>
                <Textarea id="descricao_seo" {...register('descricao_seo')} rows={3} />
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
