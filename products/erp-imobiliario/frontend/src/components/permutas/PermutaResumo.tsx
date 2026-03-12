import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { PerfilPermuta } from '@/hooks/usePermutas';
import { formatCurrency, formatDate } from '@/lib/utils';
import { DollarSign, MapPin, Home, Car } from 'lucide-react';

interface PermutaResumoProps {
  perfil: PerfilPermuta;
}

export function PermutaResumo({ perfil }: PermutaResumoProps) {
  const isImovel = perfil.natureza === 'permuta_imovel';

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-sm">Valor</span>
          </div>
          <p className="text-2xl font-bold">{formatCurrency(perfil.valor)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            {isImovel ? <Home className="w-4 h-4" /> : <Car className="w-4 h-4" />}
            <span className="text-sm">Tipo</span>
          </div>
          <p className="text-lg font-medium capitalize">
            {isImovel ? (perfil.tipo_imovel || 'Imóvel') : (perfil.tipo_veiculo || 'Veículo')}
          </p>
        </Card>
        {isImovel && perfil.cidade && (
          <Card className="p-4">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <MapPin className="w-4 h-4" />
              <span className="text-sm">Localização</span>
            </div>
            <p className="text-lg font-medium">
              {[perfil.bairro, perfil.cidade, perfil.estado].filter(Boolean).join(', ')}
            </p>
          </Card>
        )}
        {perfil.aceita_completar_diferenca && (
          <Card className="p-4">
            <div className="text-muted-foreground mb-1 text-sm">Complemento</div>
            <p className="text-lg font-bold">
              {perfil.limite_complemento ? formatCurrency(perfil.limite_complemento) : 'Sim'}
            </p>
          </Card>
        )}
      </div>

      {/* Info Grid */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">
          {isImovel ? 'Dados do Imóvel' : 'Dados do Veículo'}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          {isImovel ? (
            <>
              {perfil.tipo_imovel && (
                <div>
                  <Label className="text-muted-foreground text-xs">Tipo</Label>
                  <p className="capitalize">{perfil.tipo_imovel}</p>
                </div>
              )}
              {perfil.cep && (
                <div>
                  <Label className="text-muted-foreground text-xs">CEP</Label>
                  <p>{perfil.cep}</p>
                </div>
              )}
              {perfil.bairro && (
                <div>
                  <Label className="text-muted-foreground text-xs">Bairro</Label>
                  <p>{perfil.bairro}</p>
                </div>
              )}
              {perfil.zona && (
                <div>
                  <Label className="text-muted-foreground text-xs">Zona</Label>
                  <p>{perfil.zona}</p>
                </div>
              )}
              {perfil.condominio_nome && (
                <div>
                  <Label className="text-muted-foreground text-xs">Condomínio</Label>
                  <p>{perfil.condominio_nome}</p>
                </div>
              )}
              {perfil.quartos != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Quartos</Label>
                  <p>{perfil.quartos}</p>
                </div>
              )}
              {perfil.vagas != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Vagas</Label>
                  <p>{perfil.vagas}</p>
                </div>
              )}
            </>
          ) : (
            <>
              {perfil.marca && (
                <div>
                  <Label className="text-muted-foreground text-xs">Marca</Label>
                  <p>{perfil.marca}</p>
                </div>
              )}
              {perfil.modelo && (
                <div>
                  <Label className="text-muted-foreground text-xs">Modelo</Label>
                  <p>{perfil.modelo}</p>
                </div>
              )}
              {perfil.motor && (
                <div>
                  <Label className="text-muted-foreground text-xs">Motor</Label>
                  <p>{perfil.motor}</p>
                </div>
              )}
              {perfil.ano != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Ano</Label>
                  <p>{perfil.ano}</p>
                </div>
              )}
              {perfil.quilometragem != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Quilometragem</Label>
                  <p>{perfil.quilometragem.toLocaleString('pt-BR')} km</p>
                </div>
              )}
            </>
          )}
          <div>
            <Label className="text-muted-foreground text-xs">Status</Label>
            <Badge>{perfil.status}</Badge>
          </div>
          <div>
            <Label className="text-muted-foreground text-xs">Criado em</Label>
            <p>{formatDate(perfil.created_at)}</p>
          </div>
          {perfil.observacoes && (
            <div className="col-span-full">
              <Label className="text-muted-foreground text-xs">Observações</Label>
              <p className="whitespace-pre-wrap">{perfil.observacoes}</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
