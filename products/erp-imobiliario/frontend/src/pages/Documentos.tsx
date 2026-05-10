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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import {
  FileText,
  Upload,
  Plus,
  Trash2,
  FileCode,
  Wand2,
  File,
  FolderOpen,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import {
  useDocumentos,
  useTemplates,
  useCreateDocumento,
  useCreateTemplate,
  useGenerateDocument,
  useDeleteDocumento,
} from '@/hooks/useDocumentos';
import {
  TipoDocumento,
  DocumentoCreateData,
  TemplateCreateData,
  DocumentTemplate,
} from '@/types/documentos';
import { CardGridSkeleton } from '@/components/ui/page-skeleton';
import { DOCUMENTO_TIPO_CONFIG } from '@/lib/constants';

const TIPO_DISPLAY: Record<TipoDocumento, { icon: typeof FileText; className: string }> = {
  contrato: { icon: FileText, className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  procuracao: { icon: FileCode, className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200' },
  laudo: { icon: File, className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  certidao: { icon: FileText, className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  outro: { icon: FolderOpen, className: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200' },
};

const emptyDocForm: DocumentoCreateData = {
  nome: '',
  tipo: 'contrato',
  arquivo_url: undefined,
  imovel_id: undefined,
  cliente_id: undefined,
  proposta_id: undefined,
};

const emptyTemplateForm: TemplateCreateData = {
  nome: '',
  tipo: 'contrato',
  conteudo: '',
  variaveis: [],
};

export default function Documentos() {
  const [activeTab, setActiveTab] = useState('documentos');
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [docModalOpen, setDocModalOpen] = useState(false);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [generateModalOpen, setGenerateModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<DocumentTemplate | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [docForm, setDocForm] = useState<DocumentoCreateData>(emptyDocForm);
  const [templateForm, setTemplateForm] = useState<TemplateCreateData>(emptyTemplateForm);
  const [generateVars, setGenerateVars] = useState<Record<string, string>>({});

  const { data: documentosData, isLoading: isLoadingDocs } = useDocumentos({
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
  });
  const documentos = documentosData?.data || [];

  const { data: templatesData, isLoading: isLoadingTemplates } = useTemplates();
  const templates = templatesData?.data || [];

  const { mutate: createDocumento, isPending: isCreatingDoc } = useCreateDocumento();
  const { mutate: createTemplate, isPending: isCreatingTemplate } = useCreateTemplate();
  const { mutate: generateDocument, isPending: isGenerating } = useGenerateDocument();
  const { mutate: deleteDocumento } = useDeleteDocumento();

  const handleCreateDoc = () => {
    if (!docForm.nome || !docForm.tipo) return;
    createDocumento(docForm, {
      onSuccess: () => {
        setDocModalOpen(false);
        setDocForm(emptyDocForm);
      },
    });
  };

  const handleCreateTemplate = () => {
    if (!templateForm.nome || !templateForm.conteudo) return;
    createTemplate(templateForm, {
      onSuccess: () => {
        setTemplateModalOpen(false);
        setTemplateForm(emptyTemplateForm);
      },
    });
  };

  const handleOpenGenerate = (template: DocumentTemplate) => {
    setSelectedTemplate(template);
    const vars: Record<string, string> = {};
    (template.variaveis || []).forEach((v) => {
      vars[v] = '';
    });
    setGenerateVars(vars);
    setGenerateModalOpen(true);
  };

  const handleGenerate = () => {
    if (!selectedTemplate) return;
    generateDocument(
      {
        template_id: selectedTemplate.id,
        variables: generateVars,
      },
      {
        onSuccess: () => {
          setGenerateModalOpen(false);
          setSelectedTemplate(null);
          setGenerateVars({});
        },
      }
    );
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteDocumento(deleteId);
      setDeleteId(null);
    }
  };

  const formatBytes = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Documentos</h1>
          <p className="text-muted-foreground">Gerenciamento de documentos e templates</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
          <TabsTrigger value="templates">Templates</TabsTrigger>
        </TabsList>

        {/* Documents Tab */}
        <TabsContent value="documentos" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Tipos</SelectItem>
                <SelectItem value="contrato">Contrato</SelectItem>
                <SelectItem value="procuracao">Procuracao</SelectItem>
                <SelectItem value="laudo">Laudo</SelectItem>
                <SelectItem value="certidao">Certidao</SelectItem>
                <SelectItem value="outro">Outro</SelectItem>
              </SelectContent>
            </Select>

            <Button onClick={() => setDocModalOpen(true)}>
              <Upload className="w-4 h-4 mr-2" />
              Novo Documento
            </Button>
          </div>

          {isLoadingDocs ? (
            <CardGridSkeleton count={6} />
          ) : documentos.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Nenhum documento encontrado
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {documentos.map((doc) => {
                const tipoDisplay = TIPO_DISPLAY[doc.tipo];
                const tipoLabel = DOCUMENTO_TIPO_CONFIG[doc.tipo]?.label || doc.tipo;
                const TipoIcon = tipoDisplay.icon;

                return (
                  <Card key={doc.id} className="hover:shadow-md transition-shadow">
                    <CardContent className="pt-6">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-3 min-w-0 flex-1">
                          <div className="p-2 bg-muted rounded-lg shrink-0">
                            <TipoIcon className="h-5 w-5 text-muted-foreground" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <h3 className="font-semibold truncate">{doc.nome}</h3>
                            <div className="flex flex-wrap gap-1 mt-1">
                              <Badge className={tipoDisplay.className}>
                                {tipoLabel}
                              </Badge>
                              {doc.template_id && (
                                <Badge variant="outline">Gerado</Badge>
                              )}
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground space-y-1">
                              {doc.mime_type && <p>{doc.mime_type}</p>}
                              {doc.tamanho_bytes && <p>{formatBytes(doc.tamanho_bytes)}</p>}
                              <p>Criado em {formatDate(doc.created_at)}</p>
                            </div>
                          </div>
                        </div>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteId(doc.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>

                      {doc.arquivo_url && (
                        <div className="mt-3">
                          <a
                            href={doc.arquivo_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-primary hover:underline"
                          >
                            Abrir arquivo
                          </a>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Templates Tab */}
        <TabsContent value="templates" className="space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setTemplateModalOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Novo Template
            </Button>
          </div>

          {isLoadingTemplates ? (
            <CardGridSkeleton count={4} />
          ) : templates.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Nenhum template encontrado
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {templates.map((template) => {
                const tipoDisplay = TIPO_DISPLAY[template.tipo];
                const tipoLabel = DOCUMENTO_TIPO_CONFIG[template.tipo]?.label || template.tipo;

                return (
                  <Card key={template.id} className="hover:shadow-md transition-shadow">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">{template.nome}</CardTitle>
                        <Badge className={tipoDisplay.className}>
                          {tipoLabel}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {template.variaveis && template.variaveis.length > 0 && (
                          <div>
                            <p className="text-sm text-muted-foreground mb-1">Variaveis:</p>
                            <div className="flex flex-wrap gap-1">
                              {template.variaveis.map((v) => (
                                <Badge key={v} variant="outline" className="text-xs">
                                  {`{{${v}}}`}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="bg-muted rounded p-3 max-h-24 overflow-y-auto">
                          <pre className="text-xs whitespace-pre-wrap font-mono">
                            {template.conteudo.slice(0, 200)}
                            {template.conteudo.length > 200 ? '...' : ''}
                          </pre>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-xs text-muted-foreground">
                            Criado em {formatDate(template.created_at)}
                          </span>
                          <Button
                            size="sm"
                            onClick={() => handleOpenGenerate(template)}
                          >
                            <Wand2 className="w-4 h-4 mr-1" />
                            Gerar Documento
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Document Modal */}
      <Dialog open={docModalOpen} onOpenChange={setDocModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Novo Documento</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Nome</Label>
              <Input
                value={docForm.nome}
                onChange={(e) => setDocForm({ ...docForm, nome: e.target.value })}
                placeholder="Nome do documento"
              />
            </div>

            <div className="space-y-2">
              <Label>Tipo</Label>
              <Select
                value={docForm.tipo}
                onValueChange={(v) => setDocForm({ ...docForm, tipo: v as TipoDocumento })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contrato">Contrato</SelectItem>
                  <SelectItem value="procuracao">Procuracao</SelectItem>
                  <SelectItem value="laudo">Laudo</SelectItem>
                  <SelectItem value="certidao">Certidao</SelectItem>
                  <SelectItem value="outro">Outro</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>URL do Arquivo (opcional)</Label>
              <Input
                value={docForm.arquivo_url || ''}
                onChange={(e) => setDocForm({ ...docForm, arquivo_url: e.target.value || undefined })}
                placeholder="https://..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>ID do Imovel (opcional)</Label>
                <Input
                  value={docForm.imovel_id || ''}
                  onChange={(e) => setDocForm({ ...docForm, imovel_id: e.target.value || undefined })}
                  placeholder="UUID"
                />
              </div>
              <div className="space-y-2">
                <Label>ID do Cliente (opcional)</Label>
                <Input
                  value={docForm.cliente_id || ''}
                  onChange={(e) => setDocForm({ ...docForm, cliente_id: e.target.value || undefined })}
                  placeholder="UUID"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>ID da Proposta (opcional)</Label>
              <Input
                value={docForm.proposta_id || ''}
                onChange={(e) => setDocForm({ ...docForm, proposta_id: e.target.value || undefined })}
                placeholder="UUID"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDocModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleCreateDoc}
              disabled={isCreatingDoc || !docForm.nome}
            >
              Criar Documento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Template Modal */}
      <Dialog open={templateModalOpen} onOpenChange={setTemplateModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Novo Template</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Nome</Label>
                <Input
                  value={templateForm.nome}
                  onChange={(e) => setTemplateForm({ ...templateForm, nome: e.target.value })}
                  placeholder="Nome do template"
                />
              </div>

              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select
                  value={templateForm.tipo}
                  onValueChange={(v) => setTemplateForm({ ...templateForm, tipo: v as TipoDocumento })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="contrato">Contrato</SelectItem>
                    <SelectItem value="procuracao">Procuracao</SelectItem>
                    <SelectItem value="laudo">Laudo</SelectItem>
                    <SelectItem value="certidao">Certidao</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Conteudo do Template</Label>
              <p className="text-xs text-muted-foreground">
                Use {"{{variavel}}"} para placeholders. Ex: {"{{nome_cliente}}"}, {"{{endereco}}"}, {"{{valor}}"}
              </p>
              <Textarea
                value={templateForm.conteudo}
                onChange={(e) => setTemplateForm({ ...templateForm, conteudo: e.target.value })}
                placeholder={"CONTRATO DE COMPRA E VENDA\n\nPelo presente instrumento, {{nome_vendedor}} vende para {{nome_comprador}} o imovel localizado em {{endereco}}, pelo valor de R$ {{valor}}..."}
                rows={12}
                className="font-mono text-sm"
              />
            </div>

            <div className="space-y-2">
              <Label>Variaveis (opcionais - detectadas automaticamente)</Label>
              <Input
                value={(templateForm.variaveis || []).join(', ')}
                onChange={(e) =>
                  setTemplateForm({
                    ...templateForm,
                    variaveis: e.target.value
                      .split(',')
                      .map((v) => v.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="nome_cliente, endereco, valor"
              />
              <p className="text-xs text-muted-foreground">
                Separadas por virgula. Se vazio, serao detectadas do conteudo.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setTemplateModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleCreateTemplate}
              disabled={isCreatingTemplate || !templateForm.nome || !templateForm.conteudo}
            >
              Criar Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Document Modal */}
      <Dialog open={generateModalOpen} onOpenChange={setGenerateModalOpen}>
        <DialogContent className="sm:max-w-[500px] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Gerar Documento</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {selectedTemplate && (
              <div className="text-sm">
                <p className="font-medium">Template: {selectedTemplate.nome}</p>
                <Badge className={TIPO_DISPLAY[selectedTemplate.tipo].className}>
                  {DOCUMENTO_TIPO_CONFIG[selectedTemplate.tipo]?.label || selectedTemplate.tipo}
                </Badge>
              </div>
            )}

            {selectedTemplate?.variaveis && selectedTemplate.variaveis.length > 0 ? (
              selectedTemplate.variaveis.map((varName) => (
                <div key={varName} className="space-y-2">
                  <Label>{varName}</Label>
                  <Input
                    value={generateVars[varName] || ''}
                    onChange={(e) =>
                      setGenerateVars({ ...generateVars, [varName]: e.target.value })
                    }
                    placeholder={`Valor para {{${varName}}}`}
                  />
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                Este template nao possui variaveis definidas.
              </p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleGenerate} disabled={isGenerating}>
              <Wand2 className="w-4 h-4 mr-2" />
              Gerar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Documento</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este documento? Esta acao e irreversivel.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
