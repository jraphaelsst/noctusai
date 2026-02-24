import { useState } from 'react';
import {
  useLeaderboard,
  useMeusPontos,
  useMinhasConquistas,
  type LeaderboardEntry,
  type Conquista,
  type Pontuacao,
} from '@/hooks/useGamificacao';
import { useAuthStore } from '@/store/authStore';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Trophy,
  Star,
  Medal,
  Lock,
  Unlock,
  Zap,
  Loader2,
  User,
  Crown,
  TrendingUp,
  Award,
  CalendarDays,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Periodo = 'semana' | 'mes' | 'geral';

const periodoLabels: Record<Periodo, string> = {
  semana: 'Semana',
  mes: 'Mes',
  geral: 'Geral',
};

const formatDate = (d: string) => {
  return new Date(d).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const formatDateTime = (d: string) => {
  return new Date(d).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const rankStyles: Record<number, { bg: string; text: string; icon: React.ReactNode }> = {
  1: {
    bg: 'bg-yellow-100 border-yellow-400',
    text: 'text-yellow-700',
    icon: <Crown className="h-5 w-5 text-yellow-500" />,
  },
  2: {
    bg: 'bg-gray-100 border-gray-400',
    text: 'text-gray-600',
    icon: <Medal className="h-5 w-5 text-gray-400" />,
  },
  3: {
    bg: 'bg-amber-100 border-amber-500',
    text: 'text-amber-700',
    icon: <Medal className="h-5 w-5 text-amber-600" />,
  },
};

const acaoLabels: Record<string, string> = {
  cliente_cadastrado: 'Novo cliente cadastrado',
  visita_realizada: 'Visita realizada',
  proposta_enviada: 'Proposta enviada',
  negocio_fechado: 'Negocio fechado',
  meta_concluida: 'Meta concluida',
  avaliacao_imovel: 'Avaliacao de imovel',
  captacao_imovel: 'Captacao de imovel',
  indicacao_cliente: 'Indicacao de cliente',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Gamificacao() {
  const { user } = useAuthStore();
  const [periodo, setPeriodo] = useState<Periodo>('geral');
  const [pontosPage, setPontosPage] = useState(1);

  const { data: leaderboard, isLoading: loadingLeaderboard } = useLeaderboard(periodo);
  const { data: pontosResult, isLoading: loadingPontos } = useMeusPontos(pontosPage);
  const { data: conquistas, isLoading: loadingConquistas } = useMinhasConquistas();

  const pontuacoes: Pontuacao[] = pontosResult?.data || [];
  const totalPontos = pontosResult?.total_pontos ?? 0;
  const allConquistas: Conquista[] = conquistas || [];
  const ranking: LeaderboardEntry[] = leaderboard || [];

  const conquistasDesbloqueadas = allConquistas.filter((c) => c.desbloqueada);
  const conquistasBloqueadas = allConquistas.filter((c) => !c.desbloqueada);

  // Find current user in the leaderboard
  const myRanking = ranking.find((r) => r.user_id === user?.id);

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Gamificacao</h1>
        <p className="text-muted-foreground">
          Acompanhe sua pontuacao, conquistas e posicao no ranking da equipe
        </p>
      </div>

      {/* My Points Summary */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Meus Pontos</CardTitle>
            <Star className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{totalPontos}</div>
            <p className="text-xs text-muted-foreground">pontos acumulados</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Minha Posicao</CardTitle>
            <Trophy className="h-5 w-5 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {myRanking ? `${myRanking.rank}o` : '-'}
            </div>
            <p className="text-xs text-muted-foreground">
              no ranking {periodoLabels[periodo].toLowerCase()}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conquistas</CardTitle>
            <Award className="h-5 w-5 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {conquistasDesbloqueadas.length}
              <span className="text-lg text-muted-foreground font-normal">
                /{allConquistas.length}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">desbloqueadas</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Leaderboard */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Trophy className="h-5 w-5" />
                  Ranking
                </CardTitle>
                <Select value={periodo} onValueChange={(v) => setPeriodo(v as Periodo)}>
                  <SelectTrigger className="w-[140px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="semana">Semana</SelectItem>
                    <SelectItem value="mes">Mes</SelectItem>
                    <SelectItem value="geral">Geral</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {loadingLeaderboard ? (
                <div className="py-8 text-center text-muted-foreground">
                  <Loader2 className="h-6 w-6 mx-auto mb-2 animate-spin" />
                  Carregando ranking...
                </div>
              ) : ranking.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  <Trophy className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">Nenhum dado de ranking</p>
                  <p className="text-sm">O ranking aparecera quando pontos forem registrados</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[70px]">Posicao</TableHead>
                      <TableHead>Corretor</TableHead>
                      <TableHead className="text-right">Pontos</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ranking.map((entry) => {
                      const style = rankStyles[entry.rank];
                      const isMe = entry.user_id === user?.id;

                      return (
                        <TableRow
                          key={entry.user_id}
                          className={`${style ? `${style.bg} border` : ''} ${isMe ? 'ring-2 ring-primary/30' : ''}`}
                        >
                          <TableCell>
                            <div className="flex items-center gap-1">
                              {style ? (
                                style.icon
                              ) : (
                                <span className="text-muted-foreground font-mono text-sm ml-1">
                                  {entry.rank}
                                </span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-3">
                              {/* Avatar placeholder */}
                              <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 overflow-hidden">
                                {entry.avatar_url ? (
                                  <img
                                    src={entry.avatar_url}
                                    alt={entry.nome}
                                    className="h-full w-full object-cover"
                                  />
                                ) : (
                                  <User className="h-4 w-4 text-muted-foreground" />
                                )}
                              </div>
                              <div>
                                <span className={`font-medium text-sm ${style?.text || ''}`}>
                                  {entry.nome}
                                </span>
                                {isMe && (
                                  <Badge variant="outline" className="ml-2 text-[10px]">
                                    Voce
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            <span className={`font-bold text-lg ${style?.text || ''}`}>
                              {entry.total_pontos.toLocaleString('pt-BR')}
                            </span>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Points Activity Feed */}
        <div className="lg:col-span-1">
          <Card className="sticky top-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Zap className="h-5 w-5" />
                Atividade Recente
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loadingPontos ? (
                <div className="py-6 text-center text-muted-foreground">
                  <Loader2 className="h-5 w-5 mx-auto mb-2 animate-spin" />
                  Carregando pontos...
                </div>
              ) : pontuacoes.length === 0 ? (
                <div className="py-6 text-center text-muted-foreground">
                  <Zap className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Nenhuma atividade de pontos</p>
                  <p className="text-xs">Realize acoes para ganhar pontos!</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {pontuacoes.slice(0, 20).map((p) => (
                    <div
                      key={p.id}
                      className="flex items-start gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors"
                    >
                      <div className="mt-0.5 shrink-0">
                        <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center">
                          <TrendingUp className="h-3.5 w-3.5 text-primary" />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {acaoLabels[p.acao] || p.acao}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Badge variant="outline" className="text-[10px] text-green-600 border-green-300">
                            +{p.pontos} pts
                          </Badge>
                          <span className="text-[10px] text-muted-foreground">
                            {formatDateTime(p.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}

                  {pontuacoes.length >= 20 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => setPontosPage((p) => p + 1)}
                    >
                      Carregar mais
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Achievements / Badges */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Award className="h-5 w-5" />
            Conquistas ({conquistasDesbloqueadas.length}/{allConquistas.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingConquistas ? (
            <div className="py-8 text-center text-muted-foreground">
              <Loader2 className="h-6 w-6 mx-auto mb-2 animate-spin" />
              Carregando conquistas...
            </div>
          ) : allConquistas.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Award className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhuma conquista disponivel</p>
              <p className="text-sm">As conquistas aparecerao conforme forem configuradas</p>
            </div>
          ) : (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {/* Unlocked achievements first */}
              {conquistasDesbloqueadas.map((conquista) => (
                <div
                  key={conquista.tipo}
                  className="relative p-4 rounded-lg border-2 border-primary/30 bg-primary/5 transition-all hover:shadow-md"
                >
                  <div className="flex flex-col items-center text-center gap-2">
                    <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                      <span className="text-2xl" role="img" aria-label={conquista.nome}>
                        {conquista.icone || '🏆'}
                      </span>
                    </div>
                    <div>
                      <p className="font-semibold text-sm">{conquista.nome}</p>
                      <p className="text-xs text-muted-foreground mt-1">{conquista.descricao}</p>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-green-600">
                      <Unlock className="h-3 w-3" />
                      {conquista.desbloqueada_em ? formatDate(conquista.desbloqueada_em) : 'Desbloqueada'}
                    </div>
                  </div>
                </div>
              ))}

              {/* Locked achievements */}
              {conquistasBloqueadas.map((conquista) => (
                <div
                  key={conquista.tipo}
                  className="relative p-4 rounded-lg border border-dashed border-muted-foreground/20 bg-muted/30 opacity-60 transition-all hover:opacity-80"
                >
                  <div className="flex flex-col items-center text-center gap-2">
                    <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                      <Lock className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-semibold text-sm">{conquista.nome}</p>
                      <p className="text-xs text-muted-foreground mt-1">{conquista.descricao}</p>
                    </div>
                    <Badge variant="outline" className="text-[10px]">
                      <Lock className="h-2.5 w-2.5 mr-1" />
                      Bloqueada
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
