import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, User, Calendar, DollarSign, Wallet,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { useAdminPatient } from '@/hooks/useAdmin';
import { formatCurrency } from '@/lib/utils';

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

export default function AdminPatientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: patient, isLoading } = useAdminPatient(id);

  if (isLoading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-64 bg-muted animate-pulse rounded" />
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="container mx-auto p-6">
        <p className="text-muted-foreground">Paciente nao encontrado</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/admin/pacientes')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
        </Button>
      </div>
    );
  }

  const p = patient as Record<string, unknown>;
  const nome = (p.nome as string) ?? 'Paciente';
  const email = (p.email as string) ?? '';
  const telefone = (p.telefone as string) ?? '';
  const terapeutaNome = (p.terapeuta_nome as string) ?? null;
  const origin = (p.origin as string) ?? 'direct';
  const sessionCount = (p.session_count as number) ?? 0;
  const walletBalance = (p.wallet_balance as number) ?? 0;

  return (
    <div className="container mx-auto p-6 space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate('/admin/pacientes')}>
        <ArrowLeft className="h-4 w-4 mr-2" /> Pacientes
      </Button>

      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <Avatar className="h-16 w-16">
          <AvatarFallback className="text-lg">{getInitials(nome)}</AvatarFallback>
        </Avatar>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{nome}</h1>
          <p className="text-muted-foreground">{email}{telefone ? ` | ${telefone}` : ''}</p>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="outline">Origem: {origin}</Badge>
            {terapeutaNome && <Badge variant="secondary">Terapeuta: {terapeutaNome}</Badge>}
          </div>
        </div>
      </div>

      {/* Quick stats */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Calendar className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-sm text-muted-foreground">Total de Sessoes</p>
              <p className="text-xl font-bold">{sessionCount}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <User className="h-8 w-8 text-green-500" />
            <div>
              <p className="text-sm text-muted-foreground">Terapeuta Atual</p>
              <p className="text-lg font-semibold truncate">{terapeutaNome ?? 'Nenhum'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Wallet className="h-8 w-8 text-primary" />
            <div>
              <p className="text-sm text-muted-foreground">Saldo Carteira</p>
              <p className="text-xl font-bold">{formatCurrency(walletBalance)}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="perfil">
        <TabsList>
          <TabsTrigger value="perfil">Perfil</TabsTrigger>
          <TabsTrigger value="sessoes">Historico de Sessoes</TabsTrigger>
          <TabsTrigger value="financeiro">Transacoes</TabsTrigger>
          <TabsTrigger value="carteira">Carteira</TabsTrigger>
        </TabsList>

        <TabsContent value="perfil" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <User className="h-5 w-5" /> Dados Pessoais
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Nome</label>
                  <p className="mt-1">{nome}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Email</label>
                  <p className="mt-1">{email}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Telefone</label>
                  <p className="mt-1">{telefone || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Data de Nascimento</label>
                  <p className="mt-1">{(p.data_nascimento as string) || '-'}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sessoes" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Calendar className="h-5 w-5" /> Historico de Sessoes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Nenhuma sessao registrada.</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="financeiro" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <DollarSign className="h-5 w-5" /> Transacoes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Nenhuma transacao registrada.</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="carteira" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Wallet className="h-5 w-5" /> Movimentacoes da Carteira
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium text-muted-foreground">Saldo atual</label>
                <p className="text-2xl font-bold mt-1">{formatCurrency(walletBalance)}</p>
              </div>
              <Separator />
              <p className="text-sm text-muted-foreground">Nenhuma movimentacao registrada.</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
