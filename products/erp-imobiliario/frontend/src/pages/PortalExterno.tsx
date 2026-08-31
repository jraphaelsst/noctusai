import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Badge } from '@noctusai/seed/components/ui/badge';
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
import {
  Link2,
  Copy,
  Check,
  ExternalLink,
  Plus,
  Trash2,
  User,
  Home,
  FileText,
  DollarSign,
  ShieldAlert,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import { formatDate, formatCurrency } from '@/lib/utils';
import {
  usePortalTokens,
  useGerarLink,
  useRevogarToken,
  usePortalValidar,
  usePortalImoveis,
  usePortalContratos,
  usePortalFinanceiro,
  PortalToken,
} from '@/hooks/usePortalExterno';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

function formatExpiry(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  if (date < now) return 'Expirado';
  return formatDate(dateStr, true);
}

function isExpired(dateStr: string): boolean {
  return new Date(dateStr) < new Date();
}

// --- Public Portal View (token-based, no auth) ---

function PortalPublicoView({ token }: { token: string }) {
  const portalQuery = usePortalValidar(token);
  const imoveisQuery = usePortalImoveis(token);
  const contratosQuery = usePortalContratos(token);
  const financeiroQuery = usePortalFinanceiro(token);
  const { data: portalData, error: validationError } = portalQuery;
  const { data: imoveis } = imoveisQuery;
  const { data: contratos } = contratosQuery;
  const { data: financeiro } = financeiroQuery;
  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  const isValidatingPortal = portalQuery.isPending && !portalQuery.data;
  const showImoveisSkeleton = imoveisQuery.isPending && !imoveisQuery.data;
  const showContratosSkeleton = contratosQuery.isPending && !contratosQuery.data;
  const showFinanceiroSkeleton = financeiroQuery.isPending && !financeiroQuery.data;

  if (isValidatingPortal) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
          <p className="text-muted-foreground">Validando acesso...</p>
        </div>
      </div>
    );
  }

  if (validationError || !portalData) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6 text-center space-y-4">
            <ShieldAlert className="h-12 w-12 mx-auto text-destructive" />
            <h2 className="text-xl font-semibold">Acesso Negado</h2>
            <p className="text-muted-foreground">
              Este link de acesso e invalido ou expirou. Solicite um novo link ao seu corretor.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isProprietario = portalData.tipo === 'proprietario';

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex items-center gap-3">
        <User className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">
            Portal do {isProprietario ? 'Proprietario' : 'Locatario'}
          </h1>
          <p className="text-muted-foreground">
            Bem-vindo(a), {portalData.nome}
          </p>
        </div>
      </div>

      <div className="text-sm text-muted-foreground">
        Acesso valido ate: {formatDate(portalData.expires_at, true)}
      </div>

      {/* Property View (for owners) */}
      {isProprietario && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Home className="h-5 w-5" />
              Meus Imoveis
            </CardTitle>
          </CardHeader>
          <CardContent>
            {showImoveisSkeleton ? (
              <TableSkeleton rows={3} />
            ) : imoveis && imoveis.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Imovel</TableHead>
                    <TableHead>Endereco</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Tipo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {imoveis.map((imovel: any) => (
                    <TableRow key={imovel.id}>
                      <TableCell className="font-medium">
                        {imovel.titulo_anuncio || imovel.ref || 'Sem titulo'}
                      </TableCell>
                      <TableCell>
                        {[imovel.logradouro, imovel.numero, imovel.bairro, imovel.cidade]
                          .filter(Boolean)
                          .join(', ') || '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={imovel.status === 'ativo' ? 'default' : 'secondary'}>
                          {imovel.status || 'N/A'}
                        </Badge>
                      </TableCell>
                      <TableCell>{imovel.tipo_imovel || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="py-4 text-center text-muted-foreground">Nenhum imovel encontrado.</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Contracts View (for tenants) */}
      {!isProprietario && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Meus Contratos
            </CardTitle>
          </CardHeader>
          <CardContent>
            {showContratosSkeleton ? (
              <TableSkeleton rows={3} />
            ) : contratos && contratos.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Contrato</TableHead>
                    <TableHead>Imovel</TableHead>
                    <TableHead>Inicio</TableHead>
                    <TableHead>Fim</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {contratos.map((contrato: any) => (
                    <TableRow key={contrato.id}>
                      <TableCell className="font-medium">{contrato.numero || contrato.id.slice(0, 8)}</TableCell>
                      <TableCell>{contrato.imovel_endereco || '-'}</TableCell>
                      <TableCell>{formatDate(contrato.data_inicio)}</TableCell>
                      <TableCell>{formatDate(contrato.data_fim)}</TableCell>
                      <TableCell>
                        {contrato.valor
                          ? formatCurrency(contrato.valor)
                          : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={contrato.status === 'ativo' ? 'default' : 'secondary'}>
                          {contrato.status || 'N/A'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="py-4 text-center text-muted-foreground">Nenhum contrato encontrado.</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Financial View (for tenants) */}
      {!isProprietario && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5" />
              Pagamentos
            </CardTitle>
          </CardHeader>
          <CardContent>
            {showFinanceiroSkeleton ? (
              <TableSkeleton rows={3} />
            ) : financeiro && financeiro.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Descricao</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {financeiro.map((item: any) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-medium">{item.descricao || '-'}</TableCell>
                      <TableCell>{formatDate(item.data_vencimento)}</TableCell>
                      <TableCell>
                        {item.valor
                          ? formatCurrency(item.valor)
                          : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            item.status === 'pago'
                              ? 'default'
                              : item.status === 'atrasado'
                                ? 'destructive'
                                : 'outline'
                          }
                        >
                          {item.status || 'N/A'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="py-4 text-center text-muted-foreground">Nenhum pagamento encontrado.</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// --- Agent Management View (authenticated) ---

function PortalGerenciamentoView() {
  const tokensQuery = usePortalTokens();
  const { data: tokens } = tokensQuery;
  const showTokensSkeleton = tokensQuery.isPending && !tokensQuery.data;
  const { mutate: gerarLink, isPending: isGerando } = useGerarLink();
  const { mutate: revogarToken } = useRevogarToken();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    tipo: 'proprietario' as 'proprietario' | 'locatario',
    pessoa_id: '',
    nome: '',
    email: '',
    dias_validade: 30,
  });

  const resetForm = () => {
    setFormData({
      tipo: 'proprietario',
      pessoa_id: '',
      nome: '',
      email: '',
      dias_validade: 30,
    });
  };

  const handleGerarLink = () => {
    if (!formData.pessoa_id || !formData.nome) {
      toast.error('Preencha os campos obrigatorios (ID da pessoa e nome).');
      return;
    }
    gerarLink(
      {
        tipo: formData.tipo,
        pessoa_id: formData.pessoa_id,
        nome: formData.nome,
        email: formData.email || undefined,
        dias_validade: formData.dias_validade,
      },
      {
        onSuccess: () => {
          setDialogOpen(false);
          resetForm();
        },
      }
    );
  };

  const handleCopyLink = async (token: PortalToken) => {
    const link = token.link || `${window.location.origin}/portal-externo?token=${token.token}`;
    try {
      await navigator.clipboard.writeText(link);
      setCopiedId(token.id);
      toast.success('Link copiado!');
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error('Erro ao copiar link.');
    }
  };

  const activeTokens = useMemo(
    () => (tokens || []).filter((t) => t.is_active),
    [tokens]
  );
  const inactiveTokens = useMemo(
    () => (tokens || []).filter((t) => !t.is_active),
    [tokens]
  );

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Portal Externo</h1>
          <p className="text-muted-foreground">
            Gere links de acesso para proprietarios e locatarios
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Gerar Link
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Links Ativos</CardTitle>
            <Link2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{activeTokens.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Proprietarios</CardTitle>
            <Home className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {activeTokens.filter((t) => t.tipo === 'proprietario').length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Locatarios</CardTitle>
            <User className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {activeTokens.filter((t) => t.tipo === 'locatario').length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active Tokens */}
      <Card>
        <CardHeader>
          <CardTitle>Links de Acesso Ativos</CardTitle>
        </CardHeader>
        <CardContent>
          {showTokensSkeleton ? (
            <TableSkeleton rows={3} />
          ) : activeTokens.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Link2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhum link ativo</p>
              <p className="text-sm">Clique em "Gerar Link" para criar um novo acesso.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Validade</TableHead>
                    <TableHead>Criado em</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeTokens.map((token) => (
                    <TableRow key={token.id}>
                      <TableCell className="font-medium">
                        <div>
                          <p>{token.nome}</p>
                          {token.email && (
                            <p className="text-xs text-muted-foreground">{token.email}</p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={token.tipo === 'proprietario' ? 'default' : 'secondary'}
                        >
                          {token.tipo === 'proprietario' ? 'Proprietario' : 'Locatario'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className={isExpired(token.expires_at) ? 'text-destructive font-medium' : ''}>
                          {formatExpiry(token.expires_at)}
                        </span>
                      </TableCell>
                      <TableCell>{formatDate(token.created_at)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyLink(token)}
                            title="Copiar link"
                          >
                            {copiedId === token.id ? (
                              <Check className="h-4 w-4 text-green-600" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              const link = token.link || `${window.location.origin}/portal-externo?token=${token.token}`;
                              window.open(link, '_blank');
                            }}
                            title="Abrir portal"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => revogarToken(token.id)}
                            title="Revogar acesso"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Revoked/Inactive Tokens */}
      {inactiveTokens.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-muted-foreground">Links Revogados / Inativos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Validade</TableHead>
                    <TableHead>Criado em</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {inactiveTokens.map((token) => (
                    <TableRow key={token.id} className="opacity-60">
                      <TableCell className="font-medium">{token.nome}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {token.tipo === 'proprietario' ? 'Proprietario' : 'Locatario'}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatExpiry(token.expires_at)}</TableCell>
                      <TableCell>{formatDate(token.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Generate Link Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Gerar Link de Acesso</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Tipo de Acesso</Label>
              <Select
                value={formData.tipo}
                onValueChange={(v) => setFormData({ ...formData, tipo: v as 'proprietario' | 'locatario' })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="proprietario">Proprietario</SelectItem>
                  <SelectItem value="locatario">Locatario</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>ID da Pessoa *</Label>
              <Input
                value={formData.pessoa_id}
                onChange={(e) => setFormData({ ...formData, pessoa_id: e.target.value })}
                placeholder="UUID do proprietario ou locatario"
              />
            </div>

            <div className="space-y-2">
              <Label>Nome *</Label>
              <Input
                value={formData.nome}
                onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                placeholder="Nome completo"
              />
            </div>

            <div className="space-y-2">
              <Label>Email (opcional)</Label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="email@exemplo.com"
              />
            </div>

            <div className="space-y-2">
              <Label>Validade (dias)</Label>
              <Input
                type="number"
                min={1}
                max={365}
                value={formData.dias_validade}
                onChange={(e) => setFormData({ ...formData, dias_validade: parseInt(e.target.value) || 30 })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleGerarLink}
              disabled={isGerando || !formData.pessoa_id || !formData.nome}
            >
              {isGerando ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Gerando...
                </>
              ) : (
                'Gerar Link'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- Main Component (route entry point) ---

export default function PortalExterno() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  if (token) {
    return <PortalPublicoView token={token} />;
  }

  return <PortalGerenciamentoView />;
}
