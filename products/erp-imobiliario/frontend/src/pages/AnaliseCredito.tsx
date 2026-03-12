import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Search,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  Clock,
  Loader2,
  FileSearch,
  TrendingUp,
  User,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import {
  useAnalisesCredito,
  useConsultarCredito,
  AnaliseCredito as AnaliseType,
} from '@/hooks/useAnaliseCredito';

type StatusAnalise = 'pendente' | 'aprovado' | 'reprovado' | 'em_analise';
type FonteAnalise = 'serasa' | 'boa_vista' | 'manual';

const STATUS_CONFIG: Record<StatusAnalise, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: typeof ShieldCheck }> = {
  pendente: { label: 'Pendente', variant: 'outline', icon: Clock },
  em_analise: { label: 'Em Análise', variant: 'secondary', icon: Search },
  aprovado: { label: 'Aprovado', variant: 'default', icon: ShieldCheck },
  reprovado: { label: 'Reprovado', variant: 'destructive', icon: XCircle },
};

const FONTE_CONFIG: Record<FonteAnalise, { label: string }> = {
  serasa: { label: 'Serasa' },
  boa_vista: { label: 'Boa Vista' },
  manual: { label: 'Manual' },
};

function formatCpf(value: string): string {
  const cleaned = value.replace(/\D/g, '').slice(0, 11);
  if (cleaned.length <= 3) return cleaned;
  if (cleaned.length <= 6) return `${cleaned.slice(0, 3)}.${cleaned.slice(3)}`;
  if (cleaned.length <= 9) return `${cleaned.slice(0, 3)}.${cleaned.slice(3, 6)}.${cleaned.slice(6)}`;
  return `${cleaned.slice(0, 3)}.${cleaned.slice(3, 6)}.${cleaned.slice(6, 9)}-${cleaned.slice(9)}`;
}

function cleanCpf(value: string): string {
  return value.replace(/\D/g, '');
}

function getScoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-muted-foreground';
  if (score >= 700) return 'text-green-600';
  if (score >= 400) return 'text-yellow-600';
  return 'text-red-600';
}

function getScoreLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'N/A';
  if (score >= 700) return 'Excelente';
  if (score >= 500) return 'Bom';
  if (score >= 400) return 'Regular';
  if (score >= 300) return 'Baixo';
  return 'Muito Baixo';
}

function getScoreBgColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-gray-200 dark:bg-gray-700';
  if (score >= 700) return 'bg-green-500';
  if (score >= 400) return 'bg-yellow-500';
  return 'bg-red-500';
}

// --- Score Gauge Component ---

function ScoreGauge({ score }: { score: number | null | undefined }) {
  const safeScore = score ?? 0;
  const percentage = Math.min(Math.max(safeScore / 1000, 0), 1) * 100;

  return (
    <div className="flex flex-col items-center space-y-3">
      <div className="relative w-40 h-40">
        <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
          {/* Background circle */}
          <circle
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            className="text-gray-200 dark:text-gray-700"
          />
          {/* Score arc */}
          <circle
            cx="60"
            cy="60"
            r="50"
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${percentage * 3.14} ${314 - percentage * 3.14}`}
            className={
              safeScore >= 700
                ? 'text-green-500'
                : safeScore >= 400
                  ? 'text-yellow-500'
                  : 'text-red-500'
            }
            stroke="currentColor"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold ${getScoreColor(score)}`}>
            {score !== null && score !== undefined ? score : '--'}
          </span>
          <span className="text-xs text-muted-foreground">{getScoreLabel(score)}</span>
        </div>
      </div>

      {/* Score bar */}
      <div className="w-full max-w-xs">
        <div className="flex justify-between text-xs text-muted-foreground mb-1">
          <span>0</span>
          <span>400</span>
          <span>700</span>
          <span>1000</span>
        </div>
        <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
          <div className="flex h-full">
            <div className="bg-red-500" style={{ width: '40%' }} />
            <div className="bg-yellow-500" style={{ width: '30%' }} />
            <div className="bg-green-500" style={{ width: '30%' }} />
          </div>
        </div>
        {score !== null && score !== undefined && (
          <div className="relative h-3 mt-1">
            <div
              className="absolute w-0.5 h-3 bg-foreground rounded"
              style={{ left: `${percentage}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// --- Main Component ---

export default function AnaliseCredito() {
  // Form state
  const [cpf, setCpf] = useState('');
  const [nome, setNome] = useState('');
  const [fonte, setFonte] = useState<FonteAnalise>('serasa');

  // Filter state
  const [filtroStatus, setFiltroStatus] = useState('todos');
  const [filtroFonte, setFiltroFonte] = useState('todos');
  const [filtroCpf, setFiltroCpf] = useState('');

  // Detail dialog
  const [selectedAnalise, setSelectedAnalise] = useState<AnaliseType | null>(null);

  const { data: analises, isLoading } = useAnalisesCredito({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
    fonte: filtroFonte !== 'todos' ? filtroFonte : undefined,
    cpf: filtroCpf ? cleanCpf(filtroCpf) : undefined,
  });
  const { mutate: consultar, isPending: isConsultando } = useConsultarCredito();

  const handleConsultar = () => {
    const cpfLimpo = cleanCpf(cpf);
    if (cpfLimpo.length !== 11) {
      return;
    }
    if (!nome.trim()) {
      return;
    }

    consultar(
      {
        cpf: cpfLimpo,
        nome: nome.trim(),
        fonte,
      },
      {
        onSuccess: () => {
          setCpf('');
          setNome('');
          setFonte('serasa');
        },
      }
    );
  };

  const stats = useMemo(() => {
    if (!analises) return { total: 0, aprovados: 0, reprovados: 0, pendentes: 0 };
    return {
      total: analises.length,
      aprovados: analises.filter((a) => a.status === 'aprovado').length,
      reprovados: analises.filter((a) => a.status === 'reprovado').length,
      pendentes: analises.filter((a) => a.status === 'pendente' || a.status === 'em_analise').length,
    };
  }, [analises]);

  const cpfIsValid = cleanCpf(cpf).length === 11;

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">Analise de Credito</h1>
        <p className="text-muted-foreground">Consulte e gerencie analises de credito de clientes</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileSearch className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aprovados</CardTitle>
            <ShieldCheck className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.aprovados}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Reprovados</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats.reprovados}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">{stats.pendentes}</div>
          </CardContent>
        </Card>
      </div>

      {/* Consultation Form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Nova Consulta
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 items-end">
            <div className="space-y-2">
              <Label htmlFor="cpf">CPF *</Label>
              <Input
                id="cpf"
                value={cpf}
                onChange={(e) => setCpf(formatCpf(e.target.value))}
                placeholder="000.000.000-00"
                maxLength={14}
              />
              {cpf && !cpfIsValid && (
                <p className="text-xs text-destructive">CPF deve ter 11 digitos.</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="nome">Nome *</Label>
              <Input
                id="nome"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Nome completo"
              />
            </div>

            <div className="space-y-2">
              <Label>Fonte</Label>
              <Select value={fonte} onValueChange={(v) => setFonte(v as FonteAnalise)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="serasa">Serasa</SelectItem>
                  <SelectItem value="boa_vista">Boa Vista</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleConsultar}
              disabled={isConsultando || !cpfIsValid || !nome.trim()}
              className="h-10"
            >
              {isConsultando ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Consultando...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4 mr-2" />
                  Consultar
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="em_analise">Em Analise</SelectItem>
                <SelectItem value="aprovado">Aprovado</SelectItem>
                <SelectItem value="reprovado">Reprovado</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroFonte} onValueChange={setFiltroFonte}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Fonte" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todas as Fontes</SelectItem>
                <SelectItem value="serasa">Serasa</SelectItem>
                <SelectItem value="boa_vista">Boa Vista</SelectItem>
                <SelectItem value="manual">Manual</SelectItem>
              </SelectContent>
            </Select>

            <Input
              value={filtroCpf}
              onChange={(e) => setFiltroCpf(formatCpf(e.target.value))}
              placeholder="Filtrar por CPF..."
              className="w-[200px]"
              maxLength={14}
            />
          </div>
        </CardContent>
      </Card>

      {/* History Table */}
      <Card>
        <CardHeader>
          <CardTitle>Historico de Consultas</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <TableSkeleton rows={4} />
          ) : !analises || analises.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <FileSearch className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhuma analise encontrada</p>
              <p className="text-sm">Realize uma nova consulta para comecar.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    <TableHead>CPF</TableHead>
                    <TableHead>Nome</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Fonte</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analises.map((analise) => {
                    const statusCfg = STATUS_CONFIG[analise.status];
                    return (
                      <TableRow key={analise.id}>
                        <TableCell className="whitespace-nowrap">
                          {formatDate(analise.created_at)}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {formatCpf(analise.cpf)}
                        </TableCell>
                        <TableCell className="font-medium max-w-[150px] truncate">
                          {analise.nome}
                        </TableCell>
                        <TableCell>
                          <span className={`font-bold ${getScoreColor(analise.score)}`}>
                            {analise.score ?? '-'}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge variant={statusCfg.variant}>
                            {statusCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {FONTE_CONFIG[analise.fonte]?.label || analise.fonte}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelectedAnalise(analise)}
                          >
                            <FileSearch className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={!!selectedAnalise} onOpenChange={(open) => !open && setSelectedAnalise(null)}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Detalhes da Analise
            </DialogTitle>
          </DialogHeader>

          {selectedAnalise && (
            <div className="space-y-6">
              {/* Score Gauge */}
              <ScoreGauge score={selectedAnalise.score} />

              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Nome</p>
                  <p className="font-medium">{selectedAnalise.nome}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">CPF</p>
                  <p className="font-mono">{formatCpf(selectedAnalise.cpf)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge variant={STATUS_CONFIG[selectedAnalise.status].variant}>
                    {STATUS_CONFIG[selectedAnalise.status].label}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Fonte</p>
                  <Badge variant="outline">
                    {FONTE_CONFIG[selectedAnalise.fonte]?.label || selectedAnalise.fonte}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data da Consulta</p>
                  <p>{formatDate(selectedAnalise.created_at, true)}</p>
                </div>
                {selectedAnalise.validade && (
                  <div>
                    <p className="text-sm text-muted-foreground">Validade</p>
                    <p>{formatDate(selectedAnalise.validade)}</p>
                  </div>
                )}
              </div>

              {/* Result Details */}
              {selectedAnalise.resultado && Object.keys(selectedAnalise.resultado).length > 0 && (
                <div>
                  <h3 className="font-semibold mb-3 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Detalhes do Resultado
                  </h3>
                  <div className="bg-muted rounded-lg p-4 space-y-2">
                    {Object.entries(selectedAnalise.resultado).map(([key, value]) => (
                      <div key={key} className="flex justify-between items-center py-1 border-b border-border last:border-0">
                        <span className="text-sm text-muted-foreground capitalize">
                          {key.replace(/_/g, ' ')}
                        </span>
                        <span className="text-sm font-medium">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
