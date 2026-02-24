import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts';
import { TrendingUp, Users, Building2, DollarSign, Target } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';
import {
  useBIVendas,
  useBICaptacao,
  useBICorretores,
  useBIImoveis,
  useBIFinanceiro,
} from '@/hooks/useBI';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

const PERIODO_OPTIONS = [
  { value: '30d', label: 'Ultimos 30 dias' },
  { value: '90d', label: 'Ultimos 90 dias' },
  { value: '6m', label: 'Ultimos 6 meses' },
  { value: '1a', label: 'Ultimo ano' },
  { value: 'total', label: 'Total' },
];

const TABS = [
  { key: 'vendas', label: 'Vendas', icon: TrendingUp },
  { key: 'captacao', label: 'Captacao', icon: Target },
  { key: 'corretores', label: 'Corretores', icon: Users },
  { key: 'imoveis', label: 'Imoveis', icon: Building2 },
  { key: 'financeiro', label: 'Financeiro', icon: DollarSign },
];

export default function BI() {
  const [activeTab, setActiveTab] = useState('vendas');
  const [periodoInicio, setPeriodoInicio] = useState('');
  const [periodoFim, setPeriodoFim] = useState('');
  const [periodoCorretores, setPeriodoCorretores] = useState('30d');

  const filtrosPeriodo = {
    periodo_inicio: periodoInicio || undefined,
    periodo_fim: periodoFim || undefined,
  };

  const { data: vendas, isLoading: loadingVendas } = useBIVendas(filtrosPeriodo);
  const { data: captacao, isLoading: loadingCaptacao } = useBICaptacao();
  const { data: corretores, isLoading: loadingCorretores } = useBICorretores(periodoCorretores);
  const { data: imoveis, isLoading: loadingImoveis } = useBIImoveis();
  const { data: financeiro, isLoading: loadingFinanceiro } = useBIFinanceiro(filtrosPeriodo);

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Business Intelligence</h1>
          <p className="text-muted-foreground">Analise de dados e indicadores do negocio</p>
        </div>
        <div className="flex items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Inicio</Label>
            <Input
              type="date"
              value={periodoInicio}
              onChange={(e) => setPeriodoInicio(e.target.value)}
              className="w-[160px]"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Fim</Label>
            <Input
              type="date"
              value={periodoFim}
              onChange={(e) => setPeriodoFim(e.target.value)}
              className="w-[160px]"
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <Button
              key={tab.key}
              variant={activeTab === tab.key ? 'default' : 'outline'}
              onClick={() => setActiveTab(tab.key)}
              className="gap-2"
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </Button>
          );
        })}
      </div>

      {/* Vendas Section */}
      {activeTab === 'vendas' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Vendas</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {vendas?.total_vendas ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Ticket Medio</CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {formatCurrency(vendas?.ticket_medio ?? 0)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Taxa Conversao</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {(vendas?.taxa_conversao ?? 0).toFixed(1)}%
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Tempo Medio (dias)</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {vendas?.tempo_medio_dias ?? 0}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Vendas por Mes</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingVendas ? (
                <div className="py-8 text-center text-muted-foreground">
                  Carregando dados...
                </div>
              ) : vendas?.vendas_por_mes?.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={vendas.vendas_por_mes}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="mes" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="#8884d8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  Nenhum dado disponivel
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Captacao Section */}
      {activeTab === 'captacao' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Leads</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {captacao?.total_leads ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Taxa Conversao</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {(captacao?.taxa_conversao ?? 0).toFixed(1)}%
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Leads por Origem</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingCaptacao ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : captacao?.leads_por_origem?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={captacao.leads_por_origem}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {captacao.leads_por_origem.map((_: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Leads por Mes</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingCaptacao ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : captacao?.leads_por_mes?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={captacao.leads_por_mes}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="mes" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#82ca9d" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Corretores Section */}
      {activeTab === 'corretores' && (
        <div className="space-y-6">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <Label>Periodo</Label>
                <Select value={periodoCorretores} onValueChange={setPeriodoCorretores}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Selecione o periodo" />
                  </SelectTrigger>
                  <SelectContent>
                    {PERIODO_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Desempenho dos Corretores</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingCorretores ? (
                <div className="py-8 text-center text-muted-foreground">
                  Carregando dados...
                </div>
              ) : corretores?.ranking?.length > 0 ? (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Corretor</TableHead>
                        <TableHead className="text-right">Vendas</TableHead>
                        <TableHead className="text-right">Valor Total</TableHead>
                        <TableHead className="text-right">Comissao Total</TableHead>
                        <TableHead className="text-right">Taxa Conversao</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {corretores.ranking.map((corretor: any) => (
                        <TableRow key={corretor.corretor_id}>
                          <TableCell className="font-medium">
                            {corretor.nome || corretor.corretor_id}
                          </TableCell>
                          <TableCell className="text-right">
                            {corretor.vendas}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatCurrency(corretor.valor_total ?? 0)}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatCurrency(corretor.comissao_total ?? 0)}
                          </TableCell>
                          <TableCell className="text-right">
                            {(corretor.taxa_conversao ?? 0).toFixed(1)}%
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  Nenhum dado disponivel
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Imoveis Section */}
      {activeTab === 'imoveis' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Ativos</CardTitle>
                <Building2 className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {imoveis?.total_ativos ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Media Dias no Mercado</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {imoveis?.media_dias_mercado ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Preco/m2 Medio</CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {formatCurrency(imoveis?.preco_m2_medio ?? 0)}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Distribuicao por Tipo</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingImoveis ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : imoveis?.distribuicao_tipo?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={imoveis.distribuicao_tipo}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {imoveis.distribuicao_tipo.map((_: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Imoveis por Bairro (Top 10)</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingImoveis ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : imoveis?.imoveis_por_bairro?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={imoveis.imoveis_por_bairro.slice(0, 10)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="bairro" type="category" width={120} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#ffc658" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Financeiro Section */}
      {activeTab === 'financeiro' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Receita Total</CardTitle>
                <TrendingUp className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {formatCurrency(financeiro?.receita_total ?? 0)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Despesa Total</CardTitle>
                <DollarSign className="h-4 w-4 text-red-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">
                  {formatCurrency(financeiro?.despesa_total ?? 0)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Saldo</CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${(financeiro?.saldo ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {formatCurrency(financeiro?.saldo ?? 0)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Previsao Receita</CardTitle>
                <TrendingUp className="h-4 w-4 text-blue-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-blue-600">
                  {formatCurrency(financeiro?.previsao_receita ?? 0)}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Receitas por Mes</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingFinanceiro ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : financeiro?.receitas_por_mes?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={financeiro.receitas_por_mes}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="mes" />
                      <YAxis />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Bar dataKey="valor" fill="#82ca9d" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Despesas por Categoria</CardTitle>
              </CardHeader>
              <CardContent>
                {loadingFinanceiro ? (
                  <div className="py-8 text-center text-muted-foreground">
                    Carregando dados...
                  </div>
                ) : financeiro?.despesas_por_categoria?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={financeiro.despesas_por_categoria}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {financeiro.despesas_por_categoria.map((_: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    Nenhum dado disponivel
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
