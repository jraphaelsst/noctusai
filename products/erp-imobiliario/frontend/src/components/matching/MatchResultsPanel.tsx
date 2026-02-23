import { useState } from 'react';
import { MatchResult } from '@/types/imoveis';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatCurrency } from '@/lib/utils';
import { HomeIcon, ArrowLeftRight, FileText } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';

interface MatchResultsPanelProps {
  matches: MatchResult[];
  onClose: () => void;
}

export function MatchResultsPanel({ matches, onClose }: MatchResultsPanelProps) {
  const [selectedMatch, setSelectedMatch] = useState<MatchResult | null>(null);
  const [observacoes, setObservacoes] = useState('');
  const [creating, setCreating] = useState(false);
  const { user } = useAuthStore();

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    if (score >= 40) return 'text-orange-600';
    return 'text-red-600';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 80) return 'Alta';
    if (score >= 60) return 'Boa';
    if (score >= 40) return 'Média';
    return 'Baixa';
  };

  const handleCreateNegociacao = async () => {
    if (!selectedMatch || !user) return;

    setCreating(true);
    try {
      const { error } = await supabase.from('negociacoes').insert({
        owner_id: user.id,
        imovel_id: selectedMatch.imovel_id,
        perfil_permuta_id: selectedMatch.perfil_permuta_id,
        cliente_proprietario_id: selectedMatch.imovel?.owner_id || user.id,
        cliente_ofertante_id: selectedMatch.perfil_permuta?.cliente_ofertante_id || user.id,
        valor_imovel: selectedMatch.imovel?.preco_pedido || 0,
        valor_permuta: selectedMatch.perfil_permuta?.valor_estimado || 0,
        valor_complemento: Math.max(
          (selectedMatch.imovel?.preco_pedido || 0) - (selectedMatch.perfil_permuta?.valor_estimado || 0),
          0
        ),
        status_etapa: 'qualificacao',
        observacoes,
        timeline: [
          {
            tipo: 'criacao',
            data: new Date().toISOString(),
            descricao: 'Negociação criada a partir de match automático',
            usuario_id: user.id,
          },
        ],
      });

      if (error) throw error;

      toast.success('Negociação criada com sucesso!');
      setSelectedMatch(null);
      setObservacoes('');
      onClose();
    } catch (error: any) {
      toast.error('Erro ao criar negociação', {
        description: error.message,
      });
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Resultados do Match</span>
            <Badge variant="outline">{matches.length} encontrados</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {matches.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              Nenhum match encontrado. Tente ajustar os critérios.
            </p>
          ) : (
            matches.map((match) => (
              <Card key={`${match.imovel_id}-${match.perfil_permuta_id}`}>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <HomeIcon className="h-4 w-4 text-primary" />
                        <span className="font-medium">{match.imovel?.tipo}</span>
                        <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">
                          {match.perfil_permuta?.categoria === 'imovel'
                            ? match.perfil_permuta.tipo_imovel
                            : match.perfil_permuta?.tipo_movel}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{match.justificativa}</p>
                    </div>
                    <div className="text-right">
                      <div className={`text-2xl font-bold ${getScoreColor(match.score)}`}>
                        {match.score}%
                      </div>
                      <Badge variant="outline">{getScoreLabel(match.score)}</Badge>
                    </div>
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="flex justify-between text-sm">
                      <span>Região</span>
                      <span className="font-medium">{match.detalhes.compatibilidade_regiao}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_regiao} className="h-2" />

                    <div className="flex justify-between text-sm">
                      <span>Preço</span>
                      <span className="font-medium">{match.detalhes.compatibilidade_preco}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_preco} className="h-2" />

                    <div className="flex justify-between text-sm">
                      <span>Especificações</span>
                      <span className="font-medium">{match.detalhes.compatibilidade_specs}%</span>
                    </div>
                    <Progress value={match.detalhes.compatibilidade_specs} className="h-2" />

                    <div className="flex justify-between text-sm">
                      <span>Qualidade</span>
                      <span className="font-medium">{match.detalhes.qualidade_anuncio}%</span>
                    </div>
                    <Progress value={match.detalhes.qualidade_anuncio} className="h-2" />
                  </div>

                  <div className="flex justify-between items-center pt-4 border-t">
                    <div className="text-sm">
                      <div>Imóvel: {formatCurrency(match.imovel?.preco_pedido || 0)}</div>
                      <div>Permuta: {formatCurrency(match.perfil_permuta?.valor_estimado || 0)}</div>
                      {match.detalhes.gap_valor > 0 && (
                        <div className="font-medium text-orange-600">
                          Gap: {formatCurrency(match.detalhes.gap_valor)}
                        </div>
                      )}
                    </div>
                    <Button onClick={() => setSelectedMatch(match)}>
                      <FileText className="h-4 w-4 mr-2" />
                      Criar Negociação
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </CardContent>
      </Card>

      {/* Dialog de Criação de Negociação */}
      <Dialog open={!!selectedMatch} onOpenChange={() => setSelectedMatch(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Criar Negociação</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium mb-2">Match Selecionado:</p>
              <div className="text-sm space-y-1">
                <div>Score: <span className="font-medium">{selectedMatch?.score}%</span></div>
                <div>Imóvel: {formatCurrency(selectedMatch?.imovel?.preco_pedido || 0)}</div>
                <div>Permuta: {formatCurrency(selectedMatch?.perfil_permuta?.valor_estimado || 0)}</div>
                {selectedMatch && selectedMatch.detalhes.gap_valor > 0 && (
                  <div>Complemento: {formatCurrency(selectedMatch.detalhes.gap_valor)}</div>
                )}
              </div>
            </div>

            <div>
              <Label htmlFor="observacoes">Observações Iniciais</Label>
              <Textarea
                id="observacoes"
                value={observacoes}
                onChange={(e) => setObservacoes(e.target.value)}
                rows={4}
                placeholder="Adicione observações sobre esta negociação..."
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSelectedMatch(null)}>
                Cancelar
              </Button>
              <Button onClick={handleCreateNegociacao} disabled={creating}>
                {creating ? 'Criando...' : 'Confirmar'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
