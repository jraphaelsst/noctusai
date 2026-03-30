import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePerfilsPermuta, PerfilPermuta } from '@/hooks/usePermutas';
import { useMatches, useMatchCounts, useRecalcularMatches, useAtualizarStatusMatch } from '@/hooks/useMatches';
import { NovoPerfilPermutaDialog } from '@/components/permutas/NovoPerfilPermutaDialog';
import { MatchCard } from '@/components/shared/MatchCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Search, Plus, ArrowLeftRight, Sparkles,
  ChevronDown, ChevronUp,
  Car, Home as HomeIcon, RefreshCw,
} from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { formatCurrency } from '@/lib/utils';

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
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="perfis">
            <ArrowLeftRight className="h-4 w-4 mr-2" />Perfis de Permuta
          </TabsTrigger>
          <TabsTrigger value="matches">
            <Sparkles className="h-4 w-4 mr-2" />Matches
          </TabsTrigger>
        </TabsList>

        <TabsContent value="perfis" className="mt-6">
          <PerfisTab />
        </TabsContent>

        <TabsContent value="matches" className="mt-6">
          <MatchesTab />
        </TabsContent>
      </Tabs>

      <NovoPerfilPermutaDialog open={dialogAberto} onOpenChange={setDialogAberto} />
    </div>
  );
}

// ==================== PERFIS TAB ====================
function PerfisTab() {
  const navigate = useNavigate();
  const { data: perfis = [], isLoading } = usePerfilsPermuta();
  const { data: matchCounts = {} } = useMatchCounts();
  const [busca, setBusca] = useState('');
  const [perfilExpandido, setPerfilExpandido] = useState<string | null>(null);

  const filtrados = perfis.filter((p) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return (
      p.id.toLowerCase().includes(q) ||
      p.tipo_imovel?.toLowerCase().includes(q) ||
      p.tipo_veiculo?.toLowerCase().includes(q) ||
      p.marca?.toLowerCase().includes(q) ||
      p.cidade?.toLowerCase().includes(q) ||
      p.bairro?.toLowerCase().includes(q) ||
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

      {isLoading && <CardListSkeleton count={3} />}

      {!isLoading && filtrados.length === 0 && (
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
        const isImovel = perfil.natureza === 'permuta_imovel';

        return (
          <Card key={perfil.id} className="overflow-hidden cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate(`/permutas/${perfil.id}`)}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  {isImovel ? <HomeIcon className="h-5 w-5 text-primary" /> : <Car className="h-5 w-5 text-primary" />}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold capitalize">
                      {isImovel
                        ? (perfil.tipo_imovel || 'Imóvel')
                        : (perfil.marca ? `${perfil.marca} ${perfil.modelo || ''}` : perfil.tipo_veiculo || 'Veículo')}
                    </span>
                    <Badge variant="secondary">{isImovel ? 'Imóvel' : 'Automóvel'}</Badge>
                    <Badge>{perfil.status}</Badge>
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
                    {perfil.cidade && <div><strong>Cidade:</strong> {perfil.cidade}</div>}
                    {perfil.bairro && <div><strong>Bairro:</strong> {perfil.bairro}</div>}
                    {perfil.zona && <div><strong>Zona:</strong> {perfil.zona}</div>}
                    {perfil.quartos && <div><strong>Quartos:</strong> {perfil.quartos}</div>}
                  </>
                ) : (
                  <>
                    {perfil.marca && <div><strong>Marca:</strong> {perfil.marca}</div>}
                    {perfil.modelo && <div><strong>Modelo:</strong> {perfil.modelo}</div>}
                    {perfil.ano && <div><strong>Ano:</strong> {perfil.ano}</div>}
                    {perfil.motor && <div><strong>Motor:</strong> {perfil.motor}</div>}
                  </>
                )}
                <div><strong>Valor:</strong> {formatCurrency(perfil.valor)}</div>
                {perfil.aceita_completar_diferenca && <Badge variant="secondary">Aceita Complemento</Badge>}
              </div>

              <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                <Button variant="outline" size="sm" onClick={() => setPerfilExpandido(isExpanded ? null : perfil.id)}>
                  {isExpanded ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                  {isExpanded ? 'Ocultar' : 'Matches'}{matchCount > 0 ? ` (${matchCount})` : ''}
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

// ==================== MATCHES TAB ====================
function MatchesTab() {
  const { data: allMatches = [], isLoading } = useMatches();
  const atualizarMutation = useAtualizarStatusMatch();
  const recalcularMutation = useRecalcularMatches();
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
        <CardListSkeleton count={3} />
      ) : filtrados.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Sparkles className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-semibold">Nenhum match encontrado</p>
            <p className="text-sm mt-2">
              Matches são gerados automaticamente ou podem ser recalculados manualmente.
            </p>
            <Button
              onClick={() => recalcularMutation.mutate()}
              disabled={recalcularMutation.isPending}
              className="mt-4"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${recalcularMutation.isPending ? 'animate-spin' : ''}`} />
              Recalcular Matches
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtrados.map((match) => (
            <MatchCard key={match.id} match={match}
              onAtualizarStatus={(id, st) => atualizarMutation.mutateAsync({ matchId: id, status: st })}
              isUpdating={atualizarMutation.isPending} />
          ))}
        </div>
      )}
    </div>
  );
}

// ==================== SHARED COMPONENTS ====================
function PerfilMatchesSection({ perfilId }: { perfilId: string }) {
  const { data: matches = [], isLoading } = useMatches({ ativo_destino_id: perfilId });
  const atualizarMutation = useAtualizarStatusMatch();

  if (isLoading) return <CardListSkeleton count={3} />;
  if (matches.length === 0) return <div className="mt-4 p-4 text-center text-muted-foreground bg-muted/50 rounded-lg">Nenhum match. Tente recalcular.</div>;

  return (
    <div className="mt-4 space-y-3">
      <div className="text-sm font-medium text-muted-foreground">{matches.length} match{matches.length !== 1 ? 'es' : ''}</div>
      {matches.map((m) => (
        <MatchCard key={m.id} match={m}
          onAtualizarStatus={(id, st) => atualizarMutation.mutateAsync({ matchId: id, status: st })}
          isUpdating={atualizarMutation.isPending} />
      ))}
    </div>
  );
}
