import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { PerfilPermuta } from '@/hooks/usePermutas';
import { formatCurrency } from '@/lib/utils';

interface PermutaCriteriosProps {
  perfil: PerfilPermuta;
}

export function PermutaCriterios({ perfil }: PermutaCriteriosProps) {
  const isImovel = perfil.natureza === 'permuta_imovel';

  const hasCriteria = isImovel
    ? (perfil.faixa_preco_min || perfil.faixa_preco_max || perfil.metragem_min || perfil.metragem_max || perfil.quartos_min || perfil.vagas_min || perfil.regiao_preferida?.length)
    : (perfil.faixa_preco_min || perfil.faixa_preco_max || perfil.ano_min || perfil.ano_max || perfil.quilometragem_max);

  if (!hasCriteria) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Nenhum critério de busca definido</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Price Range */}
      {(perfil.faixa_preco_min || perfil.faixa_preco_max) && (
        <Card className="p-4 sm:p-6">
          <h3 className="text-lg font-semibold mb-3">Faixa de Preço</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            {perfil.faixa_preco_min != null && (
              <div>
                <Label className="text-muted-foreground text-xs">Mínimo</Label>
                <p className="font-medium">{formatCurrency(perfil.faixa_preco_min)}</p>
              </div>
            )}
            {perfil.faixa_preco_max != null && (
              <div>
                <Label className="text-muted-foreground text-xs">Máximo</Label>
                <p className="font-medium">{formatCurrency(perfil.faixa_preco_max)}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {isImovel ? (
        <>
          {/* Property Criteria */}
          {(perfil.metragem_min || perfil.metragem_max || perfil.quartos_min || perfil.vagas_min) && (
            <Card className="p-4 sm:p-6">
              <h3 className="text-lg font-semibold mb-3">Especificações do Imóvel</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                {perfil.metragem_min != null && (
                  <div>
                    <Label className="text-muted-foreground text-xs">Metragem Mín.</Label>
                    <p className="font-medium">{perfil.metragem_min} m²</p>
                  </div>
                )}
                {perfil.metragem_max != null && (
                  <div>
                    <Label className="text-muted-foreground text-xs">Metragem Máx.</Label>
                    <p className="font-medium">{perfil.metragem_max} m²</p>
                  </div>
                )}
                {perfil.quartos_min != null && (
                  <div>
                    <Label className="text-muted-foreground text-xs">Quartos Mín.</Label>
                    <p className="font-medium">{perfil.quartos_min}</p>
                  </div>
                )}
                {perfil.vagas_min != null && (
                  <div>
                    <Label className="text-muted-foreground text-xs">Vagas Mín.</Label>
                    <p className="font-medium">{perfil.vagas_min}</p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Region */}
          {perfil.regiao_preferida && perfil.regiao_preferida.length > 0 && (
            <Card className="p-4 sm:p-6">
              <h3 className="text-lg font-semibold mb-3">Regiões Preferidas</h3>
              <div className="flex flex-wrap gap-2">
                {perfil.regiao_preferida.map((regiao, i) => (
                  <Badge key={i} variant="secondary">{regiao}</Badge>
                ))}
              </div>
            </Card>
          )}
        </>
      ) : (
        /* Vehicle Criteria */
        (perfil.ano_min || perfil.ano_max || perfil.quilometragem_max) && (
          <Card className="p-4 sm:p-6">
            <h3 className="text-lg font-semibold mb-3">Especificações do Veículo</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              {perfil.ano_min != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Ano Mín.</Label>
                  <p className="font-medium">{perfil.ano_min}</p>
                </div>
              )}
              {perfil.ano_max != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">Ano Máx.</Label>
                  <p className="font-medium">{perfil.ano_max}</p>
                </div>
              )}
              {perfil.quilometragem_max != null && (
                <div>
                  <Label className="text-muted-foreground text-xs">KM Máx.</Label>
                  <p className="font-medium">{perfil.quilometragem_max.toLocaleString('pt-BR')} km</p>
                </div>
              )}
            </div>
          </Card>
        )
      )}

      {/* Complement */}
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold mb-3">Complemento</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <Label className="text-muted-foreground text-xs">Aceita Completar Diferença</Label>
            <p className="font-medium">{perfil.aceita_completar_diferenca ? 'Sim' : 'Não'}</p>
          </div>
          {perfil.limite_complemento != null && (
            <div>
              <Label className="text-muted-foreground text-xs">Limite</Label>
              <p className="font-medium">{formatCurrency(perfil.limite_complemento)}</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
