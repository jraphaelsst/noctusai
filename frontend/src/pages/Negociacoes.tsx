import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from '@/hooks/useUserRole';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { formatCurrency, formatDate } from '@/lib/utils';
import { FileText, TrendingUp, Clock, CheckCircle2 } from 'lucide-react';
import { Negociacao, StatusNegociacao } from '@/types/imoveis';

const STATUS_CONFIG: Record<StatusNegociacao, { label: string; color: string }> = {
  qualificacao: { label: 'Qualificação', color: 'bg-blue-500' },
  visitas: { label: 'Visitas', color: 'bg-purple-500' },
  proposta: { label: 'Proposta', color: 'bg-yellow-500' },
  negociacao: { label: 'Negociação', color: 'bg-orange-500' },
  fechado: { label: 'Fechado', color: 'bg-green-500' },
  cancelado: { label: 'Cancelado', color: 'bg-red-500' },
};

export default function Negociacoes() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();
  const [filtroStatus, setFiltroStatus] = useState<StatusNegociacao | 'todas'>('todas');

  const { data: negociacoes = [], isLoading } = useQuery({
    queryKey: ['negociacoes', user?.id, filtroStatus],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('negociacoes')
        .select('*')
        .order('created_at', { ascending: false });

      if (!isAdmin) {
        query = query.or(`cliente_proprietario_id.eq.${user.id},cliente_ofertante_id.eq.${user.id}`);
      }

      if (filtroStatus !== 'todas') {
        query = query.eq('status_etapa', filtroStatus);
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as Negociacao[];
    },
    enabled: !!user,
  });

  // Estatísticas
  const stats = {
    total: negociacoes.length,
    emAndamento: negociacoes.filter((n) => 
      ['qualificacao', 'visitas', 'proposta', 'negociacao'].includes(n.status_etapa)
    ).length,
    fechadas: negociacoes.filter((n) => n.status_etapa === 'fechado').length,
    valorTotal: negociacoes
      .filter((n) => n.status_etapa === 'fechado')
      .reduce((sum, n) => sum + Number(n.valor_imovel), 0),
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Negociações</h1>
          <p className="text-muted-foreground">
            Gerencie suas negociações de permutas
          </p>
        </div>
      </div>

      {/* Estatísticas */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.emAndamento}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Fechadas</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.fechadas}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Fechado</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(stats.valorTotal)}</div>
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <Select value={filtroStatus} onValueChange={(v) => setFiltroStatus(v as any)}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas</SelectItem>
                <SelectItem value="qualificacao">Qualificação</SelectItem>
                <SelectItem value="visitas">Visitas</SelectItem>
                <SelectItem value="proposta">Proposta</SelectItem>
                <SelectItem value="negociacao">Negociação</SelectItem>
                <SelectItem value="fechado">Fechado</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Lista de Negociações */}
      <div className="space-y-4">
        {isLoading ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              Carregando negociações...
            </CardContent>
          </Card>
        ) : negociacoes.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              Nenhuma negociação encontrada
            </CardContent>
          </Card>
        ) : (
          negociacoes.map((negociacao) => (
            <Card key={negociacao.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="h-5 w-5 text-primary" />
                      <span className="font-semibold">{negociacao.id}</span>
                      <Badge 
                        className={STATUS_CONFIG[negociacao.status_etapa].color}
                      >
                        {STATUS_CONFIG[negociacao.status_etapa].label}
                      </Badge>
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-4">
                      <div>
                        <p className="text-muted-foreground">Imóvel</p>
                        <p className="font-medium">{negociacao.imovel_id}</p>
                        <p className="text-muted-foreground">
                          {formatCurrency(negociacao.valor_imovel)}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Permuta</p>
                        <p className="font-medium">{negociacao.perfil_permuta_id}</p>
                        <p className="text-muted-foreground">
                          {formatCurrency(negociacao.valor_permuta)}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Complemento</p>
                        <p className="font-medium text-orange-600">
                          {formatCurrency(negociacao.valor_complemento)}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Criado em</p>
                        <p className="font-medium">
                          {formatDate(negociacao.created_at)}
                        </p>
                      </div>
                    </div>

                    {negociacao.observacoes && (
                      <div className="mt-4 text-sm">
                        <p className="text-muted-foreground">Observações:</p>
                        <p className="mt-1">{negociacao.observacoes}</p>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-2">
                    <Button variant="outline" size="sm">
                      Ver Detalhes
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
