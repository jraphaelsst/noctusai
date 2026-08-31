import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import {
  Building2,
  FileDown,
  FileUp,
  CheckCircle2,
  Clock,
  Plus,
  Link,
  Send,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useExtratos,
  useConciliacao,
  useImportarExtrato,
  useConciliar,
  useGerarRemessa,
  type ExtratoBancario,
  type MovimentacaoBancaria,
} from '@/hooks/useBanco';

const CONCILIADO_CONFIG: Record<string, { label: string; variant: 'default' | 'outline' }> = {
  true: { label: 'Conciliado', variant: 'default' },
  false: { label: 'Pendente', variant: 'outline' },
};

const REMESSA_STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  gerado: { label: 'Gerado', variant: 'outline' },
  enviado: { label: 'Enviado', variant: 'secondary' },
  processado: { label: 'Processado', variant: 'default' },
  erro: { label: 'Erro', variant: 'destructive' },
};

interface MovimentacaoEntry {
  data: string;
  descricao: string;
  valor: number;
  tipo: 'credito' | 'debito';
}

const emptyImportForm = {
  banco: '',
  agencia: '',
  conta: '',
  movimentacoes_text: '',
};

const emptyMovimentacao: MovimentacaoEntry = {
  data: '',
  descricao: '',
  valor: 0,
  tipo: 'credito' as const,
};

const emptyRemessaForm = {
  tipo: 'cnab240' as 'cnab240' | 'cnab400',
  banco: '',
};

export default function Banco() {
  const [activeTab, setActiveTab] = useState('extratos');
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [conciliarModalOpen, setConciliarModalOpen] = useState(false);
  const [remessaModalOpen, setRemessaModalOpen] = useState(false);
  const [importForm, setImportForm] = useState(emptyImportForm);
  const [movimentacoes, setMovimentacoes] = useState<MovimentacaoEntry[]>([{ ...emptyMovimentacao }]);
  const [selectedMovimentacao, setSelectedMovimentacao] = useState<MovimentacaoBancaria | null>(null);
  const [lancamentoIdInput, setLancamentoIdInput] = useState('');
  const [remessaForm, setRemessaForm] = useState(emptyRemessaForm);

  const extratosQuery = useExtratos();
  const { data: extratosData } = extratosQuery;
  const showExtratosSkeleton = extratosQuery.isPending && !extratosQuery.data;
  const extratos = extratosData?.data || [];

  const conciliacaoQuery = useConciliacao();
  const { data: conciliacaoData } = conciliacaoQuery;
  const showConciliacaoSkeleton = conciliacaoQuery.isPending && !conciliacaoQuery.data;
  const conciliacaoItems = conciliacaoData?.data || [];

  const { mutate: importarExtrato, isPending: isImporting } = useImportarExtrato();
  const { mutate: conciliar, isPending: isConciliando } = useConciliar();
  const { mutate: gerarRemessa, isPending: isGerandoRemessa } = useGerarRemessa();

  // Derived summary values
  const totalExtratos = extratos.length;
  const movimentacoesPendentes = conciliacaoItems.filter((m) => !m.conciliado).length;
  const remessasGeradas = 0; // Placeholder until remessas list endpoint is available

  const handleOpenImport = () => {
    setImportForm(emptyImportForm);
    setMovimentacoes([{ ...emptyMovimentacao }]);
    setImportModalOpen(true);
  };

  const handleAddMovimentacao = () => {
    setMovimentacoes([...movimentacoes, { ...emptyMovimentacao }]);
  };

  const handleRemoveMovimentacao = (index: number) => {
    if (movimentacoes.length <= 1) return;
    setMovimentacoes(movimentacoes.filter((_, i) => i !== index));
  };

  const handleMovimentacaoChange = (index: number, field: keyof MovimentacaoEntry, value: string | number) => {
    const updated = [...movimentacoes];
    updated[index] = { ...updated[index], [field]: value };
    setMovimentacoes(updated);
  };

  const handleSubmitImport = () => {
    if (!importForm.banco) return;

    const validMovimentacoes = movimentacoes.filter(
      (m) => m.data && m.descricao && m.valor > 0
    );

    if (validMovimentacoes.length === 0) return;

    importarExtrato(
      {
        banco: importForm.banco,
        agencia: importForm.agencia || undefined,
        conta: importForm.conta || undefined,
        movimentacoes: validMovimentacoes,
      },
      {
        onSuccess: () => setImportModalOpen(false),
      }
    );
  };

  const handleOpenConciliar = (movimentacao: MovimentacaoBancaria) => {
    setSelectedMovimentacao(movimentacao);
    setLancamentoIdInput('');
    setConciliarModalOpen(true);
  };

  const handleSubmitConciliar = () => {
    if (!selectedMovimentacao || !lancamentoIdInput) return;

    conciliar(
      {
        movimentacao_id: selectedMovimentacao.id,
        lancamento_id: lancamentoIdInput,
      },
      {
        onSuccess: () => setConciliarModalOpen(false),
      }
    );
  };

  const handleOpenRemessa = () => {
    setRemessaForm(emptyRemessaForm);
    setRemessaModalOpen(true);
  };

  const handleSubmitRemessa = () => {
    if (!remessaForm.banco || !remessaForm.tipo) return;

    gerarRemessa(remessaForm, {
      onSuccess: () => setRemessaModalOpen(false),
    });
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Integracao Bancaria</h1>
          <p className="text-muted-foreground">Importacao de extratos e conciliacao</p>
        </div>
        <Button onClick={handleOpenImport}>
          <FileUp className="w-4 h-4 mr-2" />
          Importar Extrato
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Extratos</CardTitle>
            <FileDown className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalExtratos}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Movimentacoes Pendentes</CardTitle>
            <Clock className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">{movimentacoesPendentes}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Remessas Geradas</CardTitle>
            <Send className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{remessasGeradas}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="extratos">Extratos</TabsTrigger>
          <TabsTrigger value="conciliacao">Conciliacao</TabsTrigger>
          <TabsTrigger value="remessas">Remessas</TabsTrigger>
        </TabsList>

        {/* Extratos Tab */}
        <TabsContent value="extratos">
          <Card>
            <CardContent className="pt-6">
              {showExtratosSkeleton ? (
                <TableSkeleton rows={4} />
              ) : extratos.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">
                  Nenhum extrato importado
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Banco</TableHead>
                        <TableHead>Agencia/Conta</TableHead>
                        <TableHead>Periodo</TableHead>
                        <TableHead className="text-right">Registros</TableHead>
                        <TableHead>Data Importacao</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {extratos.map((extrato) => (
                        <TableRow key={extrato.id}>
                          <TableCell className="font-medium">
                            <div className="flex items-center gap-2">
                              <Building2 className="h-4 w-4 text-muted-foreground" />
                              {extrato.banco}
                            </div>
                          </TableCell>
                          <TableCell>
                            {extrato.agencia && extrato.conta
                              ? `${extrato.agencia} / ${extrato.conta}`
                              : extrato.agencia || extrato.conta || '-'}
                          </TableCell>
                          <TableCell>
                            {extrato.periodo_inicio && extrato.periodo_fim
                              ? `${formatDate(extrato.periodo_inicio)} - ${formatDate(extrato.periodo_fim)}`
                              : '-'}
                          </TableCell>
                          <TableCell className="text-right">{extrato.total_registros}</TableCell>
                          <TableCell>{formatDate(extrato.data_importacao)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Conciliacao Tab */}
        <TabsContent value="conciliacao">
          <Card>
            <CardContent className="pt-6">
              {showConciliacaoSkeleton ? (
                <TableSkeleton rows={4} />
              ) : conciliacaoItems.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">
                  Nenhuma movimentacao encontrada
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Data</TableHead>
                        <TableHead>Descricao</TableHead>
                        <TableHead className="text-right">Valor</TableHead>
                        <TableHead>Conciliado</TableHead>
                        <TableHead className="text-right">Acoes</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {conciliacaoItems.map((mov) => {
                        const config = CONCILIADO_CONFIG[String(mov.conciliado)];
                        return (
                          <TableRow key={mov.id}>
                            <TableCell>{formatDate(mov.data)}</TableCell>
                            <TableCell className="max-w-[250px] truncate">
                              {mov.descricao}
                            </TableCell>
                            <TableCell
                              className={`text-right font-semibold ${
                                mov.tipo === 'credito' ? 'text-green-600' : 'text-red-600'
                              }`}
                            >
                              {mov.tipo === 'debito' ? '- ' : '+ '}
                              {formatCurrency(mov.valor)}
                            </TableCell>
                            <TableCell>
                              <Badge variant={config.variant}>{config.label}</Badge>
                            </TableCell>
                            <TableCell className="text-right">
                              {!mov.conciliado && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleOpenConciliar(mov)}
                                >
                                  <Link className="h-4 w-4 mr-1" />
                                  Conciliar
                                </Button>
                              )}
                              {mov.conciliado && (
                                <span className="text-sm text-muted-foreground flex items-center justify-end gap-1">
                                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                                  Vinculado
                                </span>
                              )}
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
        </TabsContent>

        {/* Remessas Tab */}
        <TabsContent value="remessas">
          <Card>
            <CardContent className="pt-6">
              <div className="flex justify-end mb-4">
                <Button onClick={handleOpenRemessa}>
                  <Plus className="w-4 h-4 mr-2" />
                  Gerar Remessa
                </Button>
              </div>
              <div className="py-8 text-center text-muted-foreground">
                Nenhuma remessa gerada ainda. Clique em "Gerar Remessa" para criar.
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Import Extrato Dialog */}
      <Dialog open={importModalOpen} onOpenChange={setImportModalOpen}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Importar Extrato</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Banco</Label>
                <Input
                  value={importForm.banco}
                  onChange={(e) => setImportForm({ ...importForm, banco: e.target.value })}
                  placeholder="Ex: Bradesco"
                />
              </div>
              <div className="space-y-2">
                <Label>Agencia</Label>
                <Input
                  value={importForm.agencia}
                  onChange={(e) => setImportForm({ ...importForm, agencia: e.target.value })}
                  placeholder="Ex: 1234"
                />
              </div>
              <div className="space-y-2">
                <Label>Conta</Label>
                <Input
                  value={importForm.conta}
                  onChange={(e) => setImportForm({ ...importForm, conta: e.target.value })}
                  placeholder="Ex: 56789-0"
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base">Movimentacoes</Label>
                <Button variant="outline" size="sm" onClick={handleAddMovimentacao}>
                  <Plus className="w-3 h-3 mr-1" />
                  Adicionar
                </Button>
              </div>

              {movimentacoes.map((mov, index) => (
                <div key={index} className="grid grid-cols-12 gap-2 items-end border rounded-md p-3">
                  <div className="col-span-3 space-y-1">
                    <Label className="text-xs">Data</Label>
                    <Input
                      type="date"
                      value={mov.data}
                      onChange={(e) => handleMovimentacaoChange(index, 'data', e.target.value)}
                    />
                  </div>
                  <div className="col-span-3 space-y-1">
                    <Label className="text-xs">Descricao</Label>
                    <Input
                      value={mov.descricao}
                      onChange={(e) => handleMovimentacaoChange(index, 'descricao', e.target.value)}
                      placeholder="Descricao"
                    />
                  </div>
                  <div className="col-span-2 space-y-1">
                    <Label className="text-xs">Valor (R$)</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={mov.valor || ''}
                      onChange={(e) => handleMovimentacaoChange(index, 'valor', parseFloat(e.target.value) || 0)}
                      placeholder="0,00"
                    />
                  </div>
                  <div className="col-span-2 space-y-1">
                    <Label className="text-xs">Tipo</Label>
                    <Select
                      value={mov.tipo}
                      onValueChange={(v) => handleMovimentacaoChange(index, 'tipo', v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="credito">Credito</SelectItem>
                        <SelectItem value="debito">Debito</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveMovimentacao(index)}
                      disabled={movimentacoes.length <= 1}
                      className="text-destructive hover:text-destructive"
                    >
                      Remover
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmitImport}
              disabled={
                isImporting ||
                !importForm.banco ||
                movimentacoes.every((m) => !m.data || !m.descricao || m.valor <= 0)
              }
            >
              {isImporting ? 'Importando...' : 'Importar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Conciliar Dialog */}
      <Dialog open={conciliarModalOpen} onOpenChange={setConciliarModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Conciliar Movimentacao</DialogTitle>
          </DialogHeader>

          {selectedMovimentacao && (
            <div className="grid gap-4 py-4">
              <Card>
                <CardContent className="pt-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Data</span>
                    <span className="text-sm font-medium">{formatDate(selectedMovimentacao.data)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Descricao</span>
                    <span className="text-sm font-medium max-w-[250px] truncate">
                      {selectedMovimentacao.descricao}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Valor</span>
                    <span
                      className={`text-sm font-semibold ${
                        selectedMovimentacao.tipo === 'credito' ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {selectedMovimentacao.tipo === 'debito' ? '- ' : '+ '}
                      {formatCurrency(selectedMovimentacao.valor)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Tipo</span>
                    <span className="text-sm font-medium capitalize">{selectedMovimentacao.tipo}</span>
                  </div>
                </CardContent>
              </Card>

              <div className="space-y-2">
                <Label>ID do Lancamento Financeiro</Label>
                <Input
                  value={lancamentoIdInput}
                  onChange={(e) => setLancamentoIdInput(e.target.value)}
                  placeholder="ID do lancamento para vincular"
                />
                <p className="text-xs text-muted-foreground">
                  Informe o ID do lancamento financeiro correspondente a esta movimentacao bancaria.
                </p>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setConciliarModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmitConciliar}
              disabled={isConciliando || !lancamentoIdInput}
            >
              {isConciliando ? 'Conciliando...' : 'Conciliar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Gerar Remessa Dialog */}
      <Dialog open={remessaModalOpen} onOpenChange={setRemessaModalOpen}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>Gerar Remessa</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Tipo</Label>
              <Select
                value={remessaForm.tipo}
                onValueChange={(v) => setRemessaForm({ ...remessaForm, tipo: v as 'cnab240' | 'cnab400' })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cnab240">CNAB 240</SelectItem>
                  <SelectItem value="cnab400">CNAB 400</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Banco</Label>
              <Input
                value={remessaForm.banco}
                onChange={(e) => setRemessaForm({ ...remessaForm, banco: e.target.value })}
                placeholder="Ex: Bradesco"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setRemessaModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmitRemessa}
              disabled={isGerandoRemessa || !remessaForm.banco}
            >
              {isGerandoRemessa ? 'Gerando...' : 'Gerar Remessa'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
