import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { TableSkeleton } from '@/components/ui/page-skeleton';
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
  Mail,
  Send,
  Eye,
  MailOpen,
  FileText,
  Plus,
  Pencil,
  Trash2,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import {
  useEmails,
  useEnviarEmail,
  useEmailTemplates,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  Email,
  EmailTemplate,
} from '@/hooks/useEmails';

const STATUS_EMAIL: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  rascunho: { label: 'Rascunho', variant: 'outline' },
  enviado: { label: 'Enviado', variant: 'secondary' },
  entregue: { label: 'Entregue', variant: 'default' },
  aberto: { label: 'Aberto', variant: 'default' },
  erro: { label: 'Erro', variant: 'destructive' },
};

const DIRECAO_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  enviado: { label: 'Enviado', variant: 'secondary' },
  recebido: { label: 'Recebido', variant: 'outline' },
};

interface EmailFormData {
  destinatario: string;
  assunto: string;
  corpo: string;
  cliente_id?: string;
  template_id?: string;
}

interface TemplateFormData {
  nome: string;
  assunto: string;
  corpo: string;
  variaveis: string;
}

const emptyEmailForm: EmailFormData = {
  destinatario: '',
  assunto: '',
  corpo: '',
  cliente_id: undefined,
  template_id: undefined,
};

const emptyTemplateForm: TemplateFormData = {
  nome: '',
  assunto: '',
  corpo: '',
  variaveis: '',
};

export default function Emails() {
  const [filtroDirecao, setFiltroDirecao] = useState<string>('todos');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [showTemplates, setShowTemplates] = useState(false);
  const [sendModalOpen, setSendModalOpen] = useState(false);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(null);
  const [viewingEmail, setViewingEmail] = useState<Email | null>(null);
  const [deleteTemplateId, setDeleteTemplateId] = useState<string | null>(null);
  const [emailFormData, setEmailFormData] = useState<EmailFormData>(emptyEmailForm);
  const [templateFormData, setTemplateFormData] = useState<TemplateFormData>(emptyTemplateForm);

  const { data: emailsData, isLoading } = useEmails({
    direcao: filtroDirecao !== 'todos' ? filtroDirecao : undefined,
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
  });
  const emails = emailsData?.data || [];

  const { data: templatesData, isLoading: isLoadingTemplates } = useEmailTemplates();
  const templates = templatesData?.data || [];

  const { mutate: enviarEmail, isPending: isSending } = useEnviarEmail();
  const { mutate: createTemplate, isPending: isCreatingTemplate } = useCreateTemplate();
  const { mutate: updateTemplate, isPending: isUpdatingTemplate } = useUpdateTemplate();
  const { mutate: deleteTemplate } = useDeleteTemplate();

  // Summary calculations
  const totalEnviados = emails.filter((e) => e.direcao === 'enviado').length;
  const totalAbertos = emails.filter((e) => e.status === 'aberto').length;
  const taxaAbertura = totalEnviados > 0 ? Math.round((totalAbertos / totalEnviados) * 100) : 0;
  const totalTemplates = templates.length;

  const handleOpenSend = () => {
    setEmailFormData(emptyEmailForm);
    setSendModalOpen(true);
  };

  const handleViewEmail = (email: Email) => {
    setViewingEmail(email);
    setViewModalOpen(true);
  };

  const handleOpenCreateTemplate = () => {
    setEditingTemplate(null);
    setTemplateFormData(emptyTemplateForm);
    setTemplateModalOpen(true);
  };

  const handleOpenEditTemplate = (template: EmailTemplate) => {
    setEditingTemplate(template);
    setTemplateFormData({
      nome: template.nome,
      assunto: template.assunto,
      corpo: template.corpo,
      variaveis: template.variaveis.join(', '),
    });
    setTemplateModalOpen(true);
  };

  const handleSendEmail = () => {
    if (!emailFormData.destinatario || !emailFormData.assunto || !emailFormData.corpo) {
      return;
    }

    enviarEmail(
      {
        destinatario: emailFormData.destinatario,
        assunto: emailFormData.assunto,
        corpo: emailFormData.corpo,
        cliente_id: emailFormData.cliente_id || undefined,
        template_id: emailFormData.template_id || undefined,
      },
      {
        onSuccess: () => setSendModalOpen(false),
      },
    );
  };

  const handleSubmitTemplate = () => {
    if (!templateFormData.nome || !templateFormData.assunto || !templateFormData.corpo) {
      return;
    }

    const variaveis = templateFormData.variaveis
      ? templateFormData.variaveis.split(',').map((v) => v.trim()).filter(Boolean)
      : [];

    if (editingTemplate) {
      updateTemplate(
        {
          id: editingTemplate.id,
          nome: templateFormData.nome,
          assunto: templateFormData.assunto,
          corpo: templateFormData.corpo,
          variaveis,
        },
        {
          onSuccess: () => setTemplateModalOpen(false),
        },
      );
    } else {
      createTemplate(
        {
          nome: templateFormData.nome,
          assunto: templateFormData.assunto,
          corpo: templateFormData.corpo,
          variaveis,
        },
        {
          onSuccess: () => setTemplateModalOpen(false),
        },
      );
    }
  };

  const handleDeleteTemplate = () => {
    if (deleteTemplateId) {
      deleteTemplate(deleteTemplateId);
      setDeleteTemplateId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Emails</h1>
          <p className="text-muted-foreground">Comunicacao com clientes</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowTemplates(!showTemplates)}>
            <FileText className="w-4 h-4 mr-2" />
            Templates
          </Button>
          <Button onClick={handleOpenSend}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Email
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Enviados</CardTitle>
            <Send className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">
              {totalEnviados}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Abertos</CardTitle>
            <MailOpen className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {totalAbertos}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Taxa Abertura</CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {taxaAbertura}%
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Templates</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {totalTemplates}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Templates Section */}
      {showTemplates && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Templates de Email</CardTitle>
            <Button size="sm" onClick={handleOpenCreateTemplate}>
              <Plus className="w-4 h-4 mr-2" />
              Novo Template
            </Button>
          </CardHeader>
          <CardContent>
            {isLoadingTemplates ? (
              <TableSkeleton rows={3} />
            ) : templates.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                Nenhum template encontrado
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>Assunto</TableHead>
                      <TableHead>Variaveis</TableHead>
                      <TableHead>Ativo</TableHead>
                      <TableHead className="text-right">Acoes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {templates.map((template) => (
                      <TableRow key={template.id}>
                        <TableCell className="font-medium">{template.nome}</TableCell>
                        <TableCell className="max-w-[200px] truncate">{template.assunto}</TableCell>
                        <TableCell>{template.variaveis.length}</TableCell>
                        <TableCell>
                          <Badge variant={template.ativo ? 'default' : 'secondary'}>
                            {template.ativo ? 'Ativo' : 'Inativo'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenEditTemplate(template)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDeleteTemplateId(template.id)}
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
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <Select value={filtroDirecao} onValueChange={setFiltroDirecao}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Direcao" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todas Direcoes</SelectItem>
                <SelectItem value="enviado">Enviado</SelectItem>
                <SelectItem value="recebido">Recebido</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="rascunho">Rascunho</SelectItem>
                <SelectItem value="enviado">Enviado</SelectItem>
                <SelectItem value="entregue">Entregue</SelectItem>
                <SelectItem value="aberto">Aberto</SelectItem>
                <SelectItem value="erro">Erro</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Email List Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <TableSkeleton rows={4} />
          ) : emails.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhum email encontrado
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Destinatario</TableHead>
                    <TableHead>Assunto</TableHead>
                    <TableHead>Direcao</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Aberturas</TableHead>
                    <TableHead>Data</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emails.map((email) => (
                    <TableRow key={email.id}>
                      <TableCell className="max-w-[200px] truncate">
                        {email.destinatario}
                      </TableCell>
                      <TableCell className="max-w-[250px] truncate">
                        {email.assunto}
                      </TableCell>
                      <TableCell>
                        <Badge variant={DIRECAO_CONFIG[email.direcao]?.variant || 'outline'}>
                          {DIRECAO_CONFIG[email.direcao]?.label || email.direcao}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_EMAIL[email.status]?.variant || 'outline'}>
                          {STATUS_EMAIL[email.status]?.label || email.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">{email.aberturas}</TableCell>
                      <TableCell>{formatDate(email.created_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewEmail(email)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Send Email Dialog */}
      <Dialog open={sendModalOpen} onOpenChange={setSendModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Novo Email</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Destinatario</Label>
              <Input
                type="email"
                value={emailFormData.destinatario}
                onChange={(e) => setEmailFormData({ ...emailFormData, destinatario: e.target.value })}
                placeholder="email@exemplo.com"
              />
            </div>

            <div className="space-y-2">
              <Label>Assunto</Label>
              <Input
                value={emailFormData.assunto}
                onChange={(e) => setEmailFormData({ ...emailFormData, assunto: e.target.value })}
                placeholder="Assunto do email"
              />
            </div>

            <div className="space-y-2">
              <Label>Corpo</Label>
              <Textarea
                value={emailFormData.corpo}
                onChange={(e) => setEmailFormData({ ...emailFormData, corpo: e.target.value })}
                placeholder="Conteudo do email..."
                rows={6}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Cliente ID (opcional)</Label>
                <Input
                  value={emailFormData.cliente_id || ''}
                  onChange={(e) => setEmailFormData({ ...emailFormData, cliente_id: e.target.value || undefined })}
                  placeholder="ID do cliente"
                />
              </div>

              <div className="space-y-2">
                <Label>Template (opcional)</Label>
                <Select
                  value={emailFormData.template_id || ''}
                  onValueChange={(v) => setEmailFormData({ ...emailFormData, template_id: v || undefined })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione..." />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((template) => (
                      <SelectItem key={template.id} value={template.id}>
                        {template.nome}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setSendModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSendEmail}
              disabled={isSending || !emailFormData.destinatario || !emailFormData.assunto || !emailFormData.corpo}
            >
              <Send className="w-4 h-4 mr-2" />
              Enviar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Template Create/Edit Dialog */}
      <Dialog open={templateModalOpen} onOpenChange={setTemplateModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingTemplate ? 'Editar Template' : 'Novo Template'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Nome</Label>
              <Input
                value={templateFormData.nome}
                onChange={(e) => setTemplateFormData({ ...templateFormData, nome: e.target.value })}
                placeholder="Nome do template"
              />
            </div>

            <div className="space-y-2">
              <Label>Assunto</Label>
              <Input
                value={templateFormData.assunto}
                onChange={(e) => setTemplateFormData({ ...templateFormData, assunto: e.target.value })}
                placeholder="Assunto do template"
              />
            </div>

            <div className="space-y-2">
              <Label>Corpo</Label>
              <Textarea
                value={templateFormData.corpo}
                onChange={(e) => setTemplateFormData({ ...templateFormData, corpo: e.target.value })}
                placeholder="Conteudo do template..."
                rows={6}
              />
            </div>

            <div className="space-y-2">
              <Label>Variaveis (separadas por virgula)</Label>
              <Input
                value={templateFormData.variaveis}
                onChange={(e) => setTemplateFormData({ ...templateFormData, variaveis: e.target.value })}
                placeholder="nome, email, telefone"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setTemplateModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmitTemplate}
              disabled={isCreatingTemplate || isUpdatingTemplate || !templateFormData.nome || !templateFormData.assunto || !templateFormData.corpo}
            >
              {editingTemplate ? 'Salvar' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View Email Dialog */}
      <Dialog open={viewModalOpen} onOpenChange={setViewModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              <Mail className="w-5 h-5 inline mr-2" />
              Detalhes do Email
            </DialogTitle>
          </DialogHeader>

          {viewingEmail && (
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-muted-foreground">Remetente</Label>
                  <p className="font-medium">{viewingEmail.remetente}</p>
                </div>
                <div>
                  <Label className="text-muted-foreground">Destinatario</Label>
                  <p className="font-medium">{viewingEmail.destinatario}</p>
                </div>
              </div>

              <div>
                <Label className="text-muted-foreground">Assunto</Label>
                <p className="font-medium">{viewingEmail.assunto}</p>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label className="text-muted-foreground">Direcao</Label>
                  <div className="mt-1">
                    <Badge variant={DIRECAO_CONFIG[viewingEmail.direcao]?.variant || 'outline'}>
                      {DIRECAO_CONFIG[viewingEmail.direcao]?.label || viewingEmail.direcao}
                    </Badge>
                  </div>
                </div>
                <div>
                  <Label className="text-muted-foreground">Status</Label>
                  <div className="mt-1">
                    <Badge variant={STATUS_EMAIL[viewingEmail.status]?.variant || 'outline'}>
                      {STATUS_EMAIL[viewingEmail.status]?.label || viewingEmail.status}
                    </Badge>
                  </div>
                </div>
                <div>
                  <Label className="text-muted-foreground">Data</Label>
                  <p className="font-medium">{formatDate(viewingEmail.created_at, true)}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-muted-foreground">Aberturas</Label>
                  <p className="font-medium">{viewingEmail.aberturas}</p>
                </div>
                <div>
                  <Label className="text-muted-foreground">Cliques</Label>
                  <p className="font-medium">{viewingEmail.cliques}</p>
                </div>
              </div>

              <div>
                <Label className="text-muted-foreground">Corpo</Label>
                <div className="mt-2 p-4 rounded-md bg-muted whitespace-pre-wrap text-sm">
                  {viewingEmail.corpo}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setViewModalOpen(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Template Confirmation */}
      <AlertDialog open={!!deleteTemplateId} onOpenChange={() => setDeleteTemplateId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Template</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este template? Esta acao e irreversivel.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteTemplate} className="bg-destructive hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
