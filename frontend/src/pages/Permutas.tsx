import { useState } from 'react';
import { usePerfilsPermuta } from '@/hooks/usePermutas';
import { useMatches, useMatchCounts, useRecalcularMatches, useAtualizarStatusMatch, Match } from '@/hooks/useMatches';
import { NovoPerfilPermutaDialog } from '@/components/permutas/NovoPerfilPermutaDialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import {
  Search, Plus, ArrowLeftRight, Sparkles, RefreshCcw,
  ChevronDown, ChevronUp, CheckCircle, XCircle,
  FileText, TrendingUp, Clock, CheckCircle2
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from '@/hooks/useUserRole';
import { Negociacao, StatusNegociacao } from '@/types/imoveis';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const STATUS_CONFIG: Record<StatusNegociacao, { label: string; color: string }> = {
  qualificacao: { label: 'Qualificação', color: 'bg-blue-500' },
  visitas: { label: 'Visitas', color: 'bg-purple-500' },
  proposta: { label: 'Proposta', color: 'bg-yellow-500' },
  negociacao: { label: 'Negociação', color: 'bg-orange-500' },
  fechado: { label: 'Fechado', color: 'bg-green-500' },
  cancelado: { label: 'Cancelado', color: 'bg-red-500' },
};

export default function Permutas() {
  const [dialogAberto, setDialogAberto] = useState(false);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Centro de Permutas</h1>
          <p className="text-muted-foreground">Perfis, matches e negociações de permuta</p>
        </div>
        <Button onClick={() => setDialogAberto(true)}>
          <Plus className="h-4 w-4 mr-2" />Novo Perfil
        </Button>
      </div>

      <Tabs defaultValue="perfis" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="perfis">
            <ArrowLeftRight className="h-4 w-4 mr-2" />Perfis de Permuta
          </TabsTrigger>
          <TabsTrigger value="matches">
            <Sparkles className="h-4 w-4 mr-2" />Matches
          </TabsTrigger>
          <TabsTrigger value="negociacoes">
            <FileText className="h-4 w-4 mr-2" />Negociações
          </TabsTrigger>
        </TabsList>

        <TabsContent value="perfis" className="mt-6">
          <PerfisTab />
        </TabsContent>

        <TabsContent value="matches" className="mt-6">
          <MatchesTab />
        </TabsContent>

        <TabsContent value="negociacoes" className="mt-6">
          <NegociacoesTab />
        </TabsContent>
      </Tabs>

      <NovoPerfilPermutaDialog open={dialogAberto} onOpenChange={setDialogAberto} />
    </div>
  );
}

// ==================== PERFIS TAB ====================
function PerfisTab() {
  const { data: perfis = [], isLoading } = usePerfilsPermuta();
  const { data: matchCounts = {} } = useMatchCounts();
  const recalcularMutation = useRecalcularMatches();
  const [busca, setBusca] = useState('');
  const [perfilExpandido, setPerfilExpandido] = useState<string | null>(null);

  const filtrados = perfis.filter((p) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return (
      p.id.toLowerCase().includes(q) ||
      p.tipo_imovel?.toLowerCase().includes(q) ||
      p.tipo_movel?.toLowerCase().includes(q) ||
      p.marca?.toLowerCase().includes(q) ||
      p.regiao_preferida?.some(r => r.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Buscar por tipo, região, marca..." value={busca} onChange={(e) => setBusca(e.target.value)} className="pl-10" />
          </div>
        </CardContent>
      </Card>

      {filtrados.length === 0 && !isLoading && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <ArrowLeftRight className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhum perfil de permuta encontrado</p>
            <p className="text-sm mt-1">Crie um perfil para começar a gerar matches</p>
          </CardContent>
        </Card>
      )}

      {filtrados.map((perfil) => {
        const matchCount = matchCounts[perfil.id] || 0;
        const isExpanded = perfilExpandido === perfil.id;
        const isImovel = perfil.categoria === 'imovel';

        return (
          <Card key={perfil.id} className="overflow-hidden">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <ArrowLeftRight className="h-5 w-5 text-primary" />
                  <div>
                    <span className="font-semibold capitalize">
                      {isImovel ? (perfil.tipo_imovel || 'Imóvel') : (perfil.marca ? `${perfil.marca} ${perfil.modelo || ''}` : perfil.tipo_movel || 'Veículo')}
                    </span>
                    <Badge variant="secondary" className="ml-2">{isImovel ? 'Imóvel' : 'Automóvel'}</Badge>
                    <Badge className="ml-2">{perfil.status}</Badge>
                  </div>
                </div>
                {matchCount > 0 && (
                  <Badge variant="default" className="bg-primary">
                    <Sparkles className="h-3 w-3 mr-1" />{matchCount} match{matchCount !== 1 ? 'es' : ''}
                  </Badge>
                )}
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-muted-foreground mb-4">
                {isImovel ? (
                  <>
                    {perfil.regiao_preferida?.length > 0 && <div><strong>Região:</strong> {perfil.regiao_preferida.join(', ')}</div>}
                    {perfil.quartos_min && <div><strong>Quartos:</strong> {perfil.quartos_min}+</div>}
                    {perfil.metragem_min && <div><strong>Metragem:</strong> {perfil.metragem_min}–{perfil.metragem_max || '∞'}m²</div>}
                  </>
                ) : (
                  <>
                    {perfil.marca && <div><strong>Marca:</strong> {perfil.marca}</div>}
                    {perfil.modelo && <div><strong>Modelo:</strong> {perfil.modelo}</div>}
                    {perfil.ano_min && <div><strong>Ano:</strong> {perfil.ano_min}–{perfil.ano_max || 'atual'}</div>}
                  </>
                )}
                {(perfil.faixa_preco_min || perfil.faixa_preco_max) && (
                  <div><strong>Faixa:</strong> {perfil.faixa_preco_min ? formatCurrency(perfil.faixa_preco_min) : '—'} a {perfil.faixa_preco_max ? formatCurrency(perfil.faixa_preco_max) : '—'}</div>
                )}
                {perfil.aceita_completar_diferenca && <Badge variant="secondary">Aceita Complemento</Badge>}
              </div>

              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setPerfilExpandido(isExpanded ? null : perfil.id)}>
                  {isExpanded ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                  {isExpanded ? 'Ocultar' : 'Matches'}{matchCount > 0 ? ` (${matchCount})` : ''}
                </Button>
                <Button variant="outline" size="sm" onClick={() => recalcularMutation.mutateAsync({ perfil_permuta_id: perfil.id })} disabled={recalcularMutation.isPending}>
                  <RefreshCcw className={`h-4 w-4 mr-1 ${recalcularMutation.isPending ? 'animate-spin' : ''}`} />Recalcular
                </Button>
              </div>

              {isExpanded && <PerfilMatchesSection perfilId={perfil.id} />}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ==================== MATCHES TAB (ALL MATCHES) ====================
function MatchesTab() {
  const { data: allMatches = [], isLoading } = useMatches();
  const atualizarMutation = useAtualizarStatusMatch();
  const [filtroScore, setFiltroScore] = useState('todos');

  const filtrados = allMatches.filter((m) => {
    if (filtroScore === 'alta') return m.score >= 80;
    if (filtroScore === 'boa') return m.score >= 60 && m.score < 80;
    if (filtroScore === 'media') return m.score >= 40 && m.score < 60;
    if (filtroScore === 'baixa') return m.score < 40;
    return true;
  });

  const stats = {
    total: allMatches.length,
    pendentes: allMatches.filter(m => m.status === 'pendente').length,
    aceitos: allMatches.filter(m => m.status === 'aceito').length,
    mediaScore: allMatches.length > 0 ? Math.round(allMatches.reduce((s, m) => s + m.score, 0) / allMatches.length) : 0,
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Total</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{stats.total}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Pendentes</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-yellow-600">{stats.pendentes}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Aceitos</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-green-600">{stats.aceitos}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Score Médio</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{stats.mediaScore}%</div></CardContent></Card>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Select value={filtroScore} onValueChange={setFiltroScore}>
            <SelectTrigger className="w-[200px]"><SelectValue placeholder="Filtrar por score" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos</SelectItem>
              <SelectItem value="alta">Alta (80%+)</SelectItem>
              <SelectItem value="boa">Boa (60-79%)</SelectItem>
              <SelectItem value="media">Média (40-59%)</SelectItem>
              <SelectItem value="baixa">Baixa (&lt;40%)</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Carregando matches...</CardContent></Card>
      ) : filtrados.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Nenhum match encontrado</CardContent></Card>
      ) : (
        <div className="space-y-3">
          {filtrados.map((match) => (
            <MatchCard key={match.id} match={match} onAtualizarStatus={(id, status) => atualizarMutation.mutateAsync({ matchId: id, status })} isUpdating={atualizarMutation.isPending} />
          ))}
        </div>
      )}
    </div>
  );
}

// ==================== NEGOCIAÇÕES TAB ====================
function NegociacoesTab() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();
  const [filtroStatus, setFiltroStatus] = useState<StatusNegociacao | 'todas'>('todas');

  const { data: negociacoes = [], isLoading } = useQuery({
    queryKey: ['negociacoes', user?.id, filtroStatus],
    queryFn: async () => {
      if (!user) return [];
      let query = supabase.from('negociacoes').select('*').order('created_at', { ascending: false });
      if (!isAdmin) query = query.or(`cliente_proprietario_id.eq.${user.id},cliente_ofertante_id.eq.${user.id}`);
      if (filtroStatus !== 'todas') query = query.eq('status_etapa', filtroStatus);
      const { data, error } = await query;
      if (error) throw error;
      return data as Negociacao[];
    },
    enabled: !!user,
  });

  const stats = {
    total: negociacoes.length,
    emAndamento: negociacoes.filter(n => ['qualificacao', 'visitas', 'proposta', 'negociacao'].includes(n.status_etapa)).length,
    fechadas: negociacoes.filter(n => n.status_etapa === 'fechado').length,
    valorTotal: negociacoes.filter(n => n.status_etapa === 'fechado').reduce((s, n) => s + Number(n.valor_imovel), 0),
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Total</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{stats.total}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Em Andamento</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{stats.emAndamento}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Fechadas</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-green-600">{stats.fechadas}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Valor Fechado</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{formatCurrency(stats.valorTotal)}</div></CardContent></Card>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Select value={filtroStatus} onValueChange={(v) => setFiltroStatus(v as any)}>
            <SelectTrigger className="w-[200px]"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              {Object.entries(STATUS_CONFIG).map(([key, { label }]) => (
                <SelectItem key={key} value={key}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Carregando...</CardContent></Card>
      ) : negociacoes.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Nenhuma negociação encontrada</CardContent></Card>
      ) : (
        negociacoes.map((neg) => (
          <Card key={neg.id}>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="h-5 w-5 text-primary" />
                <span className="font-semibold text-sm">{neg.id.substring(0, 8)}...</span>
                <Badge className={STATUS_CONFIG[neg.status_etapa].color}>{STATUS_CONFIG[neg.status_etapa].label}</Badge>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div><p className="text-muted-foreground">Imóvel</p><p className="font-medium">{formatCurrency(neg.valor_imovel)}</p></div>
                <div><p className="text-muted-foreground">Permuta</p><p className="font-medium">{formatCurrency(neg.valor_permuta)}</p></div>
                <div><p className="text-muted-foreground">Complemento</p><p className="font-medium text-orange-600">{formatCurrency(neg.valor_complemento)}</p></div>
                <div><p className="text-muted-foreground">Criado em</p><p className="font-medium">{formatDate(neg.created_at)}</p></div>
              </div>
              {neg.observacoes && <p className="text-sm text-muted-foreground mt-3">{neg.observacoes}</p>}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

// ==================== SHARED COMPONENTS ====================
function PerfilMatchesSection({ perfilId }: { perfilId: string }) {
  const { data: matches = [], isLoading } = useMatches({ perfil_permuta_id: perfilId });
  const atualizarMutation = useAtualizarStatusMatch();

  if (isLoading) return <div className="mt-4 p-4 text-center text-muted-foreground">Carregando...</div>;
  if (matches.length === 0) return <div className="mt-4 p-4 text-center text-muted-foreground bg-muted/50 rounded-lg">Nenhum match. Tente recalcular.</div>;

  return (
    <div className="mt-4 space-y-3">
      <div className="text-sm font-medium text-muted-foreground">{matches.length} match{matches.length !== 1 ? 'es' : ''}</div>
      {matches.map((m) => (
        <MatchCard key={m.id} match={m} onAtualizarStatus={(id, status) => atualizarMutation.mutateAsync({ matchId: id, status })} isUpdating={atualizarMutation.isPending} />
      ))}
    </div>
  );
}

function MatchCard({ match, onAtualizarStatus, isUpdating }: {
  match: Match;
  onAtualizarStatus: (id: string, status: 'aceito' | 'rejeitado') => Promise<any>;
  isUpdating: boolean;
}) {
  const scoreColor = match.score >= 80 ? 'text-green-600' : match.score >= 60 ? 'text-yellow-600' : match.score >= 40 ? 'text-orange-600' : 'text-red-600';
  const borderColor = match.score >= 60 ? '#22c55e' : match.score >= 40 ? '#f59e0b' : '#ef4444';
  const scoreLabel = match.score >= 80 ? 'Alta' : match.score >= 60 ? 'Boa' : match.score >= 40 ? 'Média' : 'Baixa';

  const statusBadge = match.status === 'aceito' ? <Badge className="bg-green-100 text-green-800">Aceito</Badge>
    : match.status === 'rejeitado' ? <Badge className="bg-red-100 text-red-800">Rejeitado</Badge>
    : match.status === 'expirado' ? <Badge className="bg-gray-100 text-gray-800">Expirado</Badge>
    : <Badge variant="outline">Pendente</Badge>;

  return (
    <Card className="border-l-4" style={{ borderLeftColor: borderColor }}>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium capitalize">{match.imovel?.tipo || 'Imóvel'}</span>
              {match.imovel?.cidade && <span className="text-sm text-muted-foreground">— {match.imovel.cidade}{match.imovel.estado ? `, ${match.imovel.estado}` : ''}</span>}
              {statusBadge}
            </div>
            <p className="text-sm text-muted-foreground">{match.justificativa}</p>
          </div>
          <div className="text-right ml-4">
            <div className={`text-2xl font-bold ${scoreColor}`}>{match.score}%</div>
            <Badge variant="outline">{scoreLabel}</Badge>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          {[
            { label: 'Região', val: match.detalhes?.compatibilidade_regiao || 0, max: 30 },
            { label: 'Preço', val: match.detalhes?.compatibilidade_preco || 0, max: 25 },
            { label: 'Specs', val: match.detalhes?.compatibilidade_specs || 0, max: 20 },
            { label: 'Qualidade', val: match.detalhes?.qualidade_anuncio || 0, max: 10 },
          ].map(({ label, val, max }) => (
            <div key={label}>
              <div className="flex justify-between text-xs"><span>{label}</span><span>{val}/{max}</span></div>
              <Progress value={val / max * 100} className="h-1.5" />
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between pt-3 border-t">
          <div className="text-sm space-x-4">
            <span>Imóvel: <strong>{formatCurrency(match.imovel?.preco_pedido || 0)}</strong></span>
            <span>Permuta: <strong>{formatCurrency(match.perfil_permuta?.valor_estimado || 0)}</strong></span>
            {match.detalhes?.gap_valor > 0 && <span className="text-orange-600">Gap: {formatCurrency(match.detalhes.gap_valor)}</span>}
          </div>
          {match.status === 'pendente' && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="text-red-600" disabled={isUpdating} onClick={() => onAtualizarStatus(match.id, 'rejeitado')}>
                <XCircle className="h-4 w-4 mr-1" />Rejeitar
              </Button>
              <Button size="sm" className="bg-green-600 hover:bg-green-700" disabled={isUpdating} onClick={() => onAtualizarStatus(match.id, 'aceito')}>
                <CheckCircle className="h-4 w-4 mr-1" />Aceitar
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
