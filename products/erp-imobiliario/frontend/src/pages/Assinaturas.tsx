import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { TableSkeleton } from '@/components/ui/page-skeleton';
import { SummaryValue } from '@/components/ui/summary-value';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  FileText,
  Send,
  Plus,
  Eye,
  Trash2,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import {
  useAssinaturas,
  useResumoAssinaturas,
  useEnviarAssinatura,
  useCancelarAssinatura,
} from '@/hooks/useAssinaturas';
import {
  StatusAssinatura,
  ProvedorAssinatura,
  Assinatura,
  EnviarAssinaturaData,
  Signatario,
} from '@/types/assinaturas';

const STATUS_CONFIG: Record<StatusAssinatura, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  enviado: { label: 'Enviado', variant: 'secondary' },
  assinado: { label: 'Assinado', variant: 'default' },
  recusado: { label: 'Recusado', variant: 'destructive' },
  expirado: { label: 'Expirado', variant: 'destructive' },
  cancelado: { label: 'Cancelado', variant: 'secondary' },
};

const PROVEDORES: { value: ProvedorAssinatura; label: string }[] = [
  { value: 'interno', label: 'Interno' },
  { value: 'clicksign', label: 'ClickSign' },
  { value: 'docusign', label: 'DocuSign' },
  { value: 'd4sign', label: 'D4Sign' },
];

const emptySignatario: Signatario = {
  nome: '',
  email: '',
  papel: '',
};

const emptyForm: EnviarAssinaturaData = {
  documento_nome: '',
  documento_url: undefined,
  contrato_id: undefined,
  signatarios: [{ ...emptySignatario }],
  provedor: 'interno',
};

export default function Assinaturas() {
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [modalOpen, setModalOpen] = useState(false);
  const [detailAssinatura, setDetailAssinatura] = useState<Assinatura | null>(null);
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [formData, setFormData] = useState<EnviarAssinaturaData>(emptyForm);

  const assinaturasQuery = useAssinaturas({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
  });
  const assinaturasData = assinaturasQuery.data;
  const showAssinaturasSkeleton = assinaturasQuery.isPending && !assinaturasQuery.data;
  const assinaturas = assinaturasData?.data || [];

  const resumoQuery = useResumoAssinaturas();
  const { data: resumo } = resumoQuery;
  const resumoNotArrived = resumoQuery.isPending && !resumoQuery.data;

  const { mutate: enviarAssinatura, isPending: isEnviando } = useEnviarAssinatura();
  const { mutate: cancelarAssinatura } = useCancelarAssinatura();

  const handleOpenCreate = () => {
    setFormData({ ...emptyForm, signatarios: [{ ...emptySignatario }] });
    setModalOpen(true);
  };

  const handleAddSignatario = () => {
    setFormData({
      ...formData,
      signatarios: [...formData.signatarios, { ...emptySignatario }],
    });
  };

  const handleRemoveSignatario = (index: number) => {
    if (formData.signatarios.length <= 1) return;
    const updated = formData.signatarios.filter((_, i) => i !== index);
    setFormData({ ...formData, signatarios: updated });
  };

  const handleSignatarioChange = (index: number, field: keyof Signatario, value: string) => {
    const updated = formData.signatarios.map((s, i) =>
      i === index ? { ...s, [field]: value } : s
    );
    setFormData({ ...formData, signatarios: updated });
  };

  const handleSubmit = () => {
    if (!formData.documento_nome || formData.signatarios.length === 0) {
      return;
    }

    const hasValidSignatario = formData.signatarios.every(
      (s) => s.nome && s.email && s.papel
    );
    if (!hasValidSignatario) return;

    enviarAssinatura(formData, {
      onSuccess: () => setModalOpen(false),
    });
  };

  const handleCancel = () => {
    if (cancelId) {
      cancelarAssinatura(cancelId);
      setCancelId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Assinaturas Digitais</h1>
          <p className="text-muted-foreground">Gerenciamento de assinaturas de documentos</p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Send className="w-4 h-4 mr-2" />
          Enviar para Assinatura
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
            <Clock className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              <SummaryValue notArrived={resumoNotArrived}>{resumo?.pendentes ?? 0}</SummaryValue>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Enviadas</CardTitle>
            <Send className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">
              <SummaryValue notArrived={resumoNotArrived}>{resumo?.enviadas ?? 0}</SummaryValue>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Assinadas</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              <SummaryValue notArrived={resumoNotArrived}>{resumo?.assinadas ?? 0}</SummaryValue>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Expiradas</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              <SummaryValue notArrived={resumoNotArrived}>{resumo?.expiradas ?? 0}</SummaryValue>
            </div>
          </CardContent>
        </Card>
      </div>

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
                <SelectItem value="enviado">Enviado</SelectItem>
                <SelectItem value="assinado">Assinado</SelectItem>
                <SelectItem value="recusado">Recusado</SelectItem>
                <SelectItem value="expirado">Expirado</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Signatures Table */}
      <Card>
        <CardContent className="pt-6">
          {showAssinaturasSkeleton ? (
            <TableSkeleton rows={4} />
          ) : assinaturas.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhuma assinatura encontrada
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Documento</TableHead>
                    <TableHead>Signatarios</TableHead>
                    <TableHead>Provedor</TableHead>
                    <TableHead>Envio</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assinaturas.map((assinatura) => (
                    <TableRow key={assinatura.id}>
                      <TableCell className="max-w-[200px] truncate">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          {assinatura.documento_nome}
                        </div>
                      </TableCell>
                      <TableCell>
                        {assinatura.signatarios.length} signatario{assinatura.signatarios.length !== 1 ? 's' : ''}
                      </TableCell>
                      <TableCell className="capitalize">
                        {PROVEDORES.find((p) => p.value === assinatura.provedor)?.label || assinatura.provedor}
                      </TableCell>
                      <TableCell>
                        {assinatura.data_envio ? formatDate(assinatura.data_envio) : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_CONFIG[assinatura.status].variant}>
                          {STATUS_CONFIG[assinatura.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDetailAssinatura(assinatura)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          {(assinatura.status === 'pendente' || assinatura.status === 'enviado') && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setCancelId(assinatura.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
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

      {/* Send for Signing Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Enviar para Assinatura</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Nome do Documento</Label>
              <Input
                value={formData.documento_nome}
                onChange={(e) => setFormData({ ...formData, documento_nome: e.target.value })}
                placeholder="Nome do documento"
              />
            </div>

            <div className="space-y-2">
              <Label>URL do Documento</Label>
              <Input
                value={formData.documento_url || ''}
                onChange={(e) => setFormData({ ...formData, documento_url: e.target.value || undefined })}
                placeholder="https://..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Provedor</Label>
                <Select
                  value={formData.provedor || 'interno'}
                  onValueChange={(v) => setFormData({ ...formData, provedor: v as ProvedorAssinatura })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROVEDORES.map((p) => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>ID do Contrato (opcional)</Label>
                <Input
                  value={formData.contrato_id || ''}
                  onChange={(e) => setFormData({ ...formData, contrato_id: e.target.value || undefined })}
                  placeholder="ID do contrato"
                />
              </div>
            </div>

            {/* Signatarios Section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base font-semibold">Signatarios</Label>
                <Button type="button" variant="outline" size="sm" onClick={handleAddSignatario}>
                  <Plus className="h-4 w-4 mr-1" />
                  Adicionar
                </Button>
              </div>

              {formData.signatarios.map((signatario, index) => (
                <div key={index} className="border rounded-lg p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">
                      Signatario {index + 1}
                    </span>
                    {formData.signatarios.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveSignatario(index)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-1">
                      <Label className="text-xs">Nome</Label>
                      <Input
                        value={signatario.nome}
                        onChange={(e) => handleSignatarioChange(index, 'nome', e.target.value)}
                        placeholder="Nome completo"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Email</Label>
                      <Input
                        type="email"
                        value={signatario.email}
                        onChange={(e) => handleSignatarioChange(index, 'email', e.target.value)}
                        placeholder="email@exemplo.com"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Papel</Label>
                      <Input
                        value={signatario.papel}
                        onChange={(e) => handleSignatarioChange(index, 'papel', e.target.value)}
                        placeholder="Ex: Comprador"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                isEnviando ||
                !formData.documento_nome ||
                formData.signatarios.length === 0 ||
                !formData.signatarios.every((s) => s.nome && s.email && s.papel)
              }
            >
              <Send className="w-4 h-4 mr-2" />
              Enviar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detailAssinatura} onOpenChange={() => setDetailAssinatura(null)}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Assinatura</DialogTitle>
          </DialogHeader>

          {detailAssinatura && (
            <div className="space-y-6 py-4">
              {/* Document Info */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <span className="font-semibold text-lg">{detailAssinatura.documento_nome}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={STATUS_CONFIG[detailAssinatura.status].variant}>
                    {STATUS_CONFIG[detailAssinatura.status].label}
                  </Badge>
                  <Badge variant="outline" className="capitalize">
                    {PROVEDORES.find((p) => p.value === detailAssinatura.provedor)?.label || detailAssinatura.provedor}
                  </Badge>
                </div>
                {detailAssinatura.documento_url && (
                  <p className="text-sm text-muted-foreground break-all">
                    URL: {detailAssinatura.documento_url}
                  </p>
                )}
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {detailAssinatura.data_envio && (
                    <div>
                      <span className="text-muted-foreground">Envio:</span>{' '}
                      {formatDate(detailAssinatura.data_envio)}
                    </div>
                  )}
                  {detailAssinatura.data_assinatura && (
                    <div>
                      <span className="text-muted-foreground">Assinatura:</span>{' '}
                      {formatDate(detailAssinatura.data_assinatura)}
                    </div>
                  )}
                  {detailAssinatura.data_expiracao && (
                    <div>
                      <span className="text-muted-foreground">Expiracao:</span>{' '}
                      {formatDate(detailAssinatura.data_expiracao)}
                    </div>
                  )}
                </div>
              </div>

              {/* Signatarios */}
              <div className="space-y-2">
                <h3 className="font-semibold">Signatarios</h3>
                <div className="space-y-2">
                  {detailAssinatura.signatarios.map((signatario, index) => (
                    <div key={index} className="border rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium">{signatario.nome}</p>
                          <p className="text-sm text-muted-foreground">{signatario.email}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm text-muted-foreground">{signatario.papel}</p>
                          {signatario.status && (
                            <Badge variant="outline" className="mt-1 text-xs">
                              {signatario.status}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Historico */}
              {detailAssinatura.historico && detailAssinatura.historico.length > 0 && (
                <div className="space-y-2">
                  <h3 className="font-semibold">Historico</h3>
                  <div className="space-y-3">
                    {detailAssinatura.historico.map((item, index) => (
                      <div key={index} className="flex gap-3 relative">
                        {index < detailAssinatura.historico.length - 1 && (
                          <div className="absolute left-[7px] top-5 bottom-0 w-px bg-border" />
                        )}
                        <div className="mt-1 h-4 w-4 rounded-full border-2 border-primary bg-background flex-shrink-0" />
                        <div className="flex-1">
                          <p className="font-medium text-sm">{item.evento}</p>
                          <p className="text-xs text-muted-foreground">{formatDate(item.data)}</p>
                          {item.detalhes && (
                            <p className="text-sm text-muted-foreground mt-1">{item.detalhes}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Cancel Confirmation */}
      <AlertDialog open={!!cancelId} onOpenChange={() => setCancelId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancelar Assinatura</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja cancelar esta assinatura? Esta acao e irreversivel.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction onClick={handleCancel} className="bg-destructive hover:bg-destructive/90">
              Cancelar Assinatura
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
