import { useState } from 'react';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { api } from '@/lib/api-client';
import { useDimobPreview } from '@/hooks/useDimob';
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
  FileText,
  Download,
  Eye,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  FileCode2,
  Building2,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatCurrency, formatDate } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const currentYear = new Date().getFullYear();
const availableYears = Array.from({ length: 6 }, (_, i) => currentYear - i);

const formatCpfCnpj = (v: string) => {
  if (!v) return '-';
  if (v.length <= 11) {
    return v.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
  }
  return v.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Dimob() {
  const [selectedYear, setSelectedYear] = useState(currentYear - 1);
  const [previewActive, setPreviewActive] = useState(false);
  const [generating, setGenerating] = useState(false);

  const { data: preview, isLoading, isError } = useDimobPreview(selectedYear, previewActive);

  const handlePreview = () => {
    setPreviewActive(true);
  };

  const handleYearChange = (year: string) => {
    setSelectedYear(Number(year));
    setPreviewActive(false);
  };

  const handleGenerateXML = async () => {
    setGenerating(true);
    try {
      const result = await api.post('/api/dimob/generate', { ano: selectedYear });

      // If the response includes XML content, trigger download
      if (result?.data?.xml || result?.xml) {
        const xmlContent = result?.data?.xml || result?.xml;
        const blob = new Blob([xmlContent], { type: 'application/xml;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `DIMOB_${selectedYear}.xml`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        toast.success('Arquivo DIMOB gerado com sucesso!');
      } else {
        toast.success('DIMOB gerada com sucesso! Verifique o download.');
      }
    } catch (error: any) {
      toast.error('Erro ao gerar DIMOB', {
        description: error.message || 'Tente novamente mais tarde',
      });
    } finally {
      setGenerating(false);
    }
  };

  const erros = preview?.validacoes?.filter((v) => v.nivel === 'erro') || [];
  const avisos = preview?.validacoes?.filter((v) => v.nivel === 'aviso') || [];
  const transacoes = preview?.transacoes || [];
  const vendas = transacoes.filter((t) => t.tipo === 'venda');
  const locacoes = transacoes.filter((t) => t.tipo === 'locacao');
  const hasErrors = erros.length > 0;

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">DIMOB</h1>
          <p className="text-muted-foreground">
            Declaracao de Informacoes sobre Atividades Imobiliarias - Receita Federal
          </p>
        </div>
      </div>

      {/* Control Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode2 className="h-5 w-5" />
            Gerar Declaracao DIMOB
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Ano-Calendario</label>
              <Select value={String(selectedYear)} onValueChange={handleYearChange}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableYears.map((year) => (
                    <SelectItem key={year} value={String(year)}>
                      {year}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button onClick={handlePreview} disabled={isLoading} variant="outline">
              {isLoading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Eye className="h-4 w-4 mr-2" />
              )}
              Pre-visualizar
            </Button>

            <Button
              onClick={handleGenerateXML}
              disabled={generating || !previewActive || hasErrors}
              title={hasErrors ? 'Corrija os erros antes de gerar o XML' : undefined}
            >
              {generating ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Download className="h-4 w-4 mr-2" />
              )}
              Gerar XML
            </Button>
          </div>

          {hasErrors && previewActive && (
            <div className="mt-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
              <p className="text-sm text-destructive font-medium">
                Existem {erros.length} erro(s) que impedem a geracao do XML. Corrija os dados antes de prosseguir.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Preview Content */}
      {previewActive && (
        <>
          {isLoading ? (
            <CardListSkeleton count={3} />
          ) : isError ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-destructive opacity-50" />
                <p className="text-lg">Erro ao carregar dados</p>
                <p className="text-sm">Tente novamente ou verifique a conexao</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-5">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Vendas</CardTitle>
                    <Building2 className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{preview?.totais?.total_vendas || 0}</div>
                    <p className="text-xs text-muted-foreground">
                      {formatCurrency(preview?.totais?.valor_total_vendas || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Locacoes</CardTitle>
                    <Building2 className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{preview?.totais?.total_locacoes || 0}</div>
                    <p className="text-xs text-muted-foreground">
                      {formatCurrency(preview?.totais?.valor_total_locacoes || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Comissoes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {formatCurrency(preview?.totais?.total_comissoes || 0)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Erros</CardTitle>
                    <AlertTriangle className="h-4 w-4 text-destructive" />
                  </CardHeader>
                  <CardContent>
                    <div className={`text-2xl font-bold ${erros.length > 0 ? 'text-destructive' : 'text-green-600'}`}>
                      {erros.length}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Avisos</CardTitle>
                    <AlertTriangle className="h-4 w-4 text-yellow-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-yellow-600">{avisos.length}</div>
                  </CardContent>
                </Card>
              </div>

              {/* Validation Results */}
              {(erros.length > 0 || avisos.length > 0) && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5" />
                      Resultado da Validacao
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {erros.map((validacao, i) => (
                      <div
                        key={`erro-${i}`}
                        className="flex items-start gap-3 p-3 bg-destructive/10 border border-destructive/20 rounded-lg"
                      >
                        <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge variant="destructive" className="text-xs">
                              Erro
                            </Badge>
                            <span className="text-sm font-medium">{validacao.campo}</span>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">{validacao.mensagem}</p>
                        </div>
                      </div>
                    ))}
                    {avisos.map((validacao, i) => (
                      <div
                        key={`aviso-${i}`}
                        className="flex items-start gap-3 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg"
                      >
                        <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 shrink-0" />
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary" className="text-xs bg-yellow-100 text-yellow-800">
                              Aviso
                            </Badge>
                            <span className="text-sm font-medium">{validacao.campo}</span>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">{validacao.mensagem}</p>
                        </div>
                      </div>
                    ))}
                    {erros.length === 0 && avisos.length === 0 && (
                      <div className="flex items-center gap-2 text-green-600">
                        <CheckCircle2 className="h-5 w-5" />
                        <span className="font-medium">Todos os dados estao validos!</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Transactions Tables */}
              {vendas.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      Vendas ({vendas.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Data</TableHead>
                          <TableHead>Imovel</TableHead>
                          <TableHead>Comprador</TableHead>
                          <TableHead>CPF/CNPJ</TableHead>
                          <TableHead className="text-right">Valor</TableHead>
                          <TableHead className="text-right">Comissao</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {vendas.map((t) => (
                          <TableRow key={t.id}>
                            <TableCell>{formatDate(t.data)}</TableCell>
                            <TableCell className="max-w-[200px] truncate" title={t.imovel_endereco}>
                              {t.imovel_endereco}
                            </TableCell>
                            <TableCell>{t.nome_comprador}</TableCell>
                            <TableCell className="font-mono text-xs">
                              {formatCpfCnpj(t.cpf_cnpj_comprador)}
                            </TableCell>
                            <TableCell className="text-right font-semibold">
                              {formatCurrency(t.valor)}
                            </TableCell>
                            <TableCell className="text-right">
                              {t.comissao ? formatCurrency(t.comissao) : '-'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {locacoes.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      Locacoes ({locacoes.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Data</TableHead>
                          <TableHead>Imovel</TableHead>
                          <TableHead>Locatario</TableHead>
                          <TableHead>CPF/CNPJ</TableHead>
                          <TableHead className="text-right">Valor</TableHead>
                          <TableHead className="text-right">Comissao</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {locacoes.map((t) => (
                          <TableRow key={t.id}>
                            <TableCell>{formatDate(t.data)}</TableCell>
                            <TableCell className="max-w-[200px] truncate" title={t.imovel_endereco}>
                              {t.imovel_endereco}
                            </TableCell>
                            <TableCell>{t.nome_comprador}</TableCell>
                            <TableCell className="font-mono text-xs">
                              {formatCpfCnpj(t.cpf_cnpj_comprador)}
                            </TableCell>
                            <TableCell className="text-right font-semibold">
                              {formatCurrency(t.valor)}
                            </TableCell>
                            <TableCell className="text-right">
                              {t.comissao ? formatCurrency(t.comissao) : '-'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {transacoes.length === 0 && (
                <Card>
                  <CardContent className="py-12 text-center text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="text-lg">Nenhuma transacao encontrada para {selectedYear}</p>
                    <p className="text-sm">
                      Verifique se existem vendas ou locacoes registradas neste periodo
                    </p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </>
      )}

      {/* Instructions when no preview */}
      {!previewActive && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <FileCode2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Selecione o ano e clique em "Pre-visualizar"</p>
            <p className="text-sm mt-1">
              O sistema ira verificar todas as transacoes imobiliarias do periodo e
              validar os dados para geracao da DIMOB
            </p>
            <div className="mt-6 max-w-md mx-auto text-left space-y-2">
              <p className="text-sm font-medium text-foreground">O que sera incluido:</p>
              <ul className="text-sm space-y-1 list-disc list-inside">
                <li>Vendas de imoveis intermediadas</li>
                <li>Contratos de locacao administrados</li>
                <li>Comissoes recebidas sobre transacoes</li>
                <li>Dados de compradores, vendedores e locatarios</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
