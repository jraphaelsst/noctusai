import { useState } from 'react';
import {
  useDistribuicaoConfig,
  useDistribuicaoFila,
  useUpdateDistribuicaoConfig,
  useAtribuirLead,
} from '@/hooks/useDistribuicao';
import { useClientes } from '@/hooks/useClientes';
import { useProfiles } from '@/hooks/useProfiles';
import type { ModoDistribuicao } from '@/types/locacoes';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Settings,
  Users,
  ArrowRightCircle,
  Loader2,
  UserPlus,
  CheckCircle2,
  Circle,
  Shuffle,
  MapPin,
  Star,
  Hand,
} from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { CardListSkeleton } from '@/components/ui/page-skeleton';

const modoLabels: Record<ModoDistribuicao, { label: string; descricao: string }> = {
  manual: {
    label: 'Manual',
    descricao: 'Leads sao atribuidos manualmente pelo gestor',
  },
  round_robin: {
    label: 'Round Robin',
    descricao: 'Distribuicao automatica em sequencia circular',
  },
  por_regiao: {
    label: 'Por Regiao',
    descricao: 'Leads direcionados ao corretor da regiao do imovel',
  },
  por_especialidade: {
    label: 'Por Especialidade',
    descricao: 'Leads direcionados conforme especialidade do corretor',
  },
};

const modoIcons: Record<ModoDistribuicao, React.ReactNode> = {
  manual: <Hand className="h-4 w-4" />,
  round_robin: <Shuffle className="h-4 w-4" />,
  por_regiao: <MapPin className="h-4 w-4" />,
  por_especialidade: <Star className="h-4 w-4" />,
};

export default function Distribuicao() {
  const configQuery = useDistribuicaoConfig();
  const filaQuery = useDistribuicaoFila();
  const { data: config } = configQuery;
  const { data: fila } = filaQuery;
  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  const showConfigSkeleton = configQuery.isPending && !configQuery.data;
  const showFilaSkeleton = filaQuery.isPending && !filaQuery.data;
  const { data: profiles } = useProfiles();
  const { data: clientes } = useClientes();
  const updateConfig = useUpdateDistribuicaoConfig();
  const atribuirLead = useAtribuirLead();

  const [selectedLeadId, setSelectedLeadId] = useState('');
  const [selectedCorretorId, setSelectedCorretorId] = useState('auto');
  const [buscaLead, setBuscaLead] = useState('');

  // Local state for agent checklist (optimistic)
  const corretoresAtivos = new Set(config?.corretores_ativos || []);

  const handleModoChange = (modo: ModoDistribuicao) => {
    updateConfig.mutate({ modo });
  };

  const handleToggleCorretor = (corretorId: string) => {
    const novosAtivos = new Set(corretoresAtivos);
    if (novosAtivos.has(corretorId)) {
      novosAtivos.delete(corretorId);
    } else {
      novosAtivos.add(corretorId);
    }
    updateConfig.mutate({ corretores_ativos: Array.from(novosAtivos) });
  };

  const handleAtribuir = () => {
    if (!selectedLeadId) return;
    atribuirLead.mutate(
      {
        cliente_id: selectedLeadId,
        corretor_id: selectedCorretorId === 'auto' ? undefined : selectedCorretorId,
      },
      {
        onSuccess: () => {
          setSelectedLeadId('');
          setSelectedCorretorId('auto');
        },
      },
    );
  };

  // Filter clients for lead search
  const clientesList = clientes || [];
  const clientesFiltrados = buscaLead
    ? clientesList.filter(
        (c: any) =>
          c.nome?.toLowerCase().includes(buscaLead.toLowerCase()) ||
          c.email?.toLowerCase().includes(buscaLead.toLowerCase()),
      )
    : clientesList;

  const allProfiles = profiles || [];

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Distribuicao de Leads</h1>
        <p className="text-muted-foreground">
          Configure como novos leads sao distribuidos entre os corretores da equipe
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Config Panel - Left Column */}
        <div className="lg:col-span-1 space-y-6">
          {/* Current Mode */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Settings className="h-5 w-5" />
                Modo de Distribuicao
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {showConfigSkeleton ? (
                <CardListSkeleton count={2} />
              ) : (
                <>
                  <Select
                    value={config?.modo || 'manual'}
                    onValueChange={(v) => handleModoChange(v as ModoDistribuicao)}
                    disabled={updateConfig.isPending}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(modoLabels) as ModoDistribuicao[]).map((modo) => (
                        <SelectItem key={modo} value={modo}>
                          <div className="flex items-center gap-2">
                            {modoIcons[modo]}
                            {modoLabels[modo].label}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {config?.modo && (
                    <div className="bg-muted p-3 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        {modoIcons[config.modo]}
                        <span className="font-medium text-sm">{modoLabels[config.modo].label}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {modoLabels[config.modo].descricao}
                      </p>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Active Agents Checklist */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Users className="h-5 w-5" />
                Corretores Ativos
              </CardTitle>
            </CardHeader>
            <CardContent>
              {allProfiles.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Nenhum corretor cadastrado
                </p>
              ) : (
                <div className="space-y-3">
                  {allProfiles.map((profile: any) => {
                    const isActive = corretoresAtivos.has(profile.id);
                    return (
                      <div
                        key={profile.id}
                        className="flex items-center gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors"
                      >
                        <Checkbox
                          id={`corretor-${profile.id}`}
                          checked={isActive}
                          onCheckedChange={() => handleToggleCorretor(profile.id)}
                          disabled={updateConfig.isPending}
                        />
                        <label
                          htmlFor={`corretor-${profile.id}`}
                          className="flex-1 cursor-pointer"
                        >
                          <span className="text-sm font-medium">{profile.nome}</span>
                          {profile.email && (
                            <span className="text-xs text-muted-foreground block">
                              {profile.email}
                            </span>
                          )}
                        </label>
                        {isActive && (
                          <Badge variant="outline" className="text-green-600 border-green-600">
                            Ativo
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                  <p className="text-xs text-muted-foreground pt-2">
                    {corretoresAtivos.size} de {allProfiles.length} corretores ativos
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Queue Visualization */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <ArrowRightCircle className="h-5 w-5" />
                Fila de Distribuicao
              </CardTitle>
            </CardHeader>
            <CardContent>
              {showFilaSkeleton ? (
                <CardListSkeleton count={3} />
              ) : !fila || fila.corretores_ativos.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">
                  <Users className="h-10 w-10 mx-auto mb-3 opacity-50" />
                  <p>Nenhum corretor na fila</p>
                  <p className="text-sm">Ative corretores no painel ao lado para iniciar</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Badge variant="secondary">{modoLabels[fila.modo]?.label || fila.modo}</Badge>
                    <span>-</span>
                    <span>Posicao atual: {fila.proximo_corretor_idx + 1}</span>
                  </div>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[60px]">Ordem</TableHead>
                        <TableHead>Corretor</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead className="text-center">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fila.corretores_ativos.map((corretor, index) => (
                        <TableRow
                          key={corretor.id}
                          className={corretor.is_next ? 'bg-primary/5 border-l-2 border-l-primary' : ''}
                        >
                          <TableCell className="font-mono text-muted-foreground">
                            {index + 1}
                          </TableCell>
                          <TableCell className="font-medium">
                            {corretor.nome}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-sm">
                            {corretor.email}
                          </TableCell>
                          <TableCell className="text-center">
                            {corretor.is_next ? (
                              <Badge className="bg-primary">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                Proximo
                              </Badge>
                            ) : (
                              <Circle className="h-4 w-4 mx-auto text-muted-foreground/40" />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Manual Assignment */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <UserPlus className="h-5 w-5" />
                Atribuicao Manual
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Selecione um lead e opcionalmente um corretor para fazer a atribuicao manual.
                Se nenhum corretor for selecionado, o sistema usara o modo configurado.
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                {/* Lead selector */}
                <div className="space-y-2">
                  <label className="text-sm font-medium">Lead (Cliente)</label>
                  <Input
                    placeholder="Buscar lead por nome ou email..."
                    value={buscaLead}
                    onChange={(e) => setBuscaLead(e.target.value)}
                  />
                  <Select value={selectedLeadId} onValueChange={setSelectedLeadId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione um lead" />
                    </SelectTrigger>
                    <SelectContent>
                      {clientesFiltrados.length === 0 ? (
                        <div className="py-2 px-3 text-sm text-muted-foreground">
                          Nenhum lead encontrado
                        </div>
                      ) : (
                        clientesFiltrados.slice(0, 50).map((cliente: any) => (
                          <SelectItem key={cliente.id} value={cliente.id}>
                            {cliente.nome}{' '}
                            {cliente.email ? `(${cliente.email})` : ''}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>

                {/* Agent selector */}
                <div className="space-y-2">
                  <label className="text-sm font-medium">Corretor (opcional)</label>
                  <Select value={selectedCorretorId} onValueChange={setSelectedCorretorId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Automatico (modo atual)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Automatico (modo atual)</SelectItem>
                      {allProfiles
                        .filter((p: any) => corretoresAtivos.has(p.id))
                        .map((profile: any) => (
                          <SelectItem key={profile.id} value={profile.id}>
                            {profile.nome}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button
                onClick={handleAtribuir}
                disabled={!selectedLeadId || atribuirLead.isPending}
                className="w-full sm:w-auto"
              >
                {atribuirLead.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <UserPlus className="h-4 w-4 mr-2" />
                )}
                Atribuir Lead
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
