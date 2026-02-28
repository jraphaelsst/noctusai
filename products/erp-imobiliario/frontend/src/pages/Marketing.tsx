import { useState } from 'react';
import {
  useCampanhas,
  useCreateCampanha,
  useUpdateCampanha,
  useDeleteCampanha,
  useEnviarCampanha,
  useAlertasMarketing,
  type Campanha,
} from '@/hooks/useMarketing';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Search,
  Plus,
  Mail,
  MessageCircle,
  Bell,
  Send,
  Trash2,
  Eye,
  MousePointerClick,
  BarChart3,
  Megaphone,
} from 'lucide-react';

const STATUS_MAP: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  rascunho: { label: 'Rascunho', variant: 'secondary' },
  ativa: { label: 'Ativa', variant: 'default' },
  pausada: { label: 'Pausada', variant: 'outline' },
  concluida: { label: 'Concluida', variant: 'secondary' },
};

const TIPO_MAP: Record<string, { label: string; icon: typeof Mail }> = {
  email: { label: 'E-mail', icon: Mail },
  whatsapp: { label: 'WhatsApp', icon: MessageCircle },
  alerta_imovel: { label: 'Alerta de Imovel', icon: Bell },
};

export default function Marketing() {
  const [busca, setBusca] = useState('');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [dialogAberto, setDialogAberto] = useState(false);
  const [detalheCampanha, setDetalheCampanha] = useState<Campanha | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [tabAtiva, setTabAtiva] = useState('campanhas');

  // Form state
  const [formNome, setFormNome] = useState('');
  const [formTipo, setFormTipo] = useState<'email' | 'whatsapp' | 'alerta_imovel'>('email');
  const [formTemplate, setFormTemplate] = useState('');
  const [formFiltroOrigem, setFormFiltroOrigem] = useState('');
  const [formFiltroEtapa, setFormFiltroEtapa] = useState('');

  const { data: campanhasData, isLoading } = useCampanhas({
    status: filtroStatus === 'todos' ? undefined : filtroStatus,
  });
  const { data: alertas = [], isLoading: loadingAlertas } = useAlertasMarketing();
  const createMutation = useCreateCampanha();
  const updateMutation = useUpdateCampanha();
  const deleteMutation = useDeleteCampanha();
  const enviarMutation = useEnviarCampanha();

  const campanhas = campanhasData?.data || [];

  const filtradas = campanhas.filter((c) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return c.nome.toLowerCase().includes(q);
  });

  const resetForm = () => {
    setFormNome('');
    setFormTipo('email');
    setFormTemplate('');
    setFormFiltroOrigem('');
    setFormFiltroEtapa('');
  };

  const handleCreate = () => {
    if (!formNome || !formTemplate) return;
    const filtros: Record<string, string> = {};
    if (formFiltroOrigem) filtros.origem = formFiltroOrigem;
    if (formFiltroEtapa) filtros.etapa = formFiltroEtapa;

    createMutation.mutate(
      { nome: formNome, tipo: formTipo, template: formTemplate, filtros },
      {
        onSuccess: () => {
          setDialogAberto(false);
          resetForm();
        },
      }
    );
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      setDeleteId(null);
    }
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Marketing</h1>
          <p className="text-muted-foreground">Campanhas de e-mail, WhatsApp e alertas de imoveis</p>
        </div>
        <Button onClick={() => { resetForm(); setDialogAberto(true); }}>
          <Plus className="h-4 w-4 mr-2" />Nova Campanha
        </Button>
      </div>

      <Tabs value={tabAtiva} onValueChange={setTabAtiva}>
        <TabsList>
          <TabsTrigger value="campanhas">Campanhas</TabsTrigger>
          <TabsTrigger value="alertas">Alertas de Imoveis</TabsTrigger>
        </TabsList>

        {/* Campanhas Tab */}
        <TabsContent value="campanhas" className="space-y-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Buscar campanhas..."
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    className="pl-10"
                  />
                </div>
                <Select value={filtroStatus} onValueChange={setFiltroStatus}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Todos os status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todos">Todos</SelectItem>
                    <SelectItem value="rascunho">Rascunho</SelectItem>
                    <SelectItem value="ativa">Ativa</SelectItem>
                    <SelectItem value="pausada">Pausada</SelectItem>
                    <SelectItem value="concluida">Concluida</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {isLoading ? (
            <Card><CardContent className="py-8 text-center text-muted-foreground">Carregando...</CardContent></Card>
          ) : filtradas.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <Megaphone className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg">Nenhuma campanha encontrada</p>
                <p className="text-sm mt-1">Crie sua primeira campanha de marketing</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtradas.map((campanha) => {
                const tipoInfo = TIPO_MAP[campanha.tipo] || TIPO_MAP.email;
                const statusInfo = STATUS_MAP[campanha.status] || STATUS_MAP.rascunho;
                const TipoIcon = tipoInfo.icon;

                return (
                  <Card key={campanha.id} className="hover:shadow-md transition-shadow">
                    <CardContent className="pt-6 space-y-3">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <TipoIcon className="h-5 w-5 text-primary shrink-0" />
                          <h3 className="font-semibold truncate">{campanha.nome}</h3>
                        </div>
                        <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                      </div>

                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <span>{tipoInfo.label}</span>
                        <span className="mx-1">-</span>
                        <span>{new Date(campanha.created_at).toLocaleDateString('pt-BR')}</span>
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="p-2 bg-muted rounded">
                          <Send className="h-3 w-3 mx-auto mb-1 text-muted-foreground" />
                          <div className="text-sm font-semibold">{campanha.total_enviados}</div>
                          <div className="text-xs text-muted-foreground">Enviados</div>
                        </div>
                        <div className="p-2 bg-muted rounded">
                          <Eye className="h-3 w-3 mx-auto mb-1 text-muted-foreground" />
                          <div className="text-sm font-semibold">{campanha.total_abertos}</div>
                          <div className="text-xs text-muted-foreground">Abertos</div>
                        </div>
                        <div className="p-2 bg-muted rounded">
                          <MousePointerClick className="h-3 w-3 mx-auto mb-1 text-muted-foreground" />
                          <div className="text-sm font-semibold">{campanha.total_cliques}</div>
                          <div className="text-xs text-muted-foreground">Cliques</div>
                        </div>
                      </div>

                      <div className="flex gap-2 pt-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() => setDetalheCampanha(campanha)}
                        >
                          <BarChart3 className="h-3 w-3 mr-1" />Detalhes
                        </Button>
                        {campanha.status === 'rascunho' && (
                          <Button
                            size="sm"
                            className="flex-1"
                            onClick={() => enviarMutation.mutate(campanha.id)}
                            disabled={enviarMutation.isPending}
                          >
                            <Send className="h-3 w-3 mr-1" />Enviar
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteId(campanha.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Alertas Tab */}
        <TabsContent value="alertas" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Alertas de Imoveis
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Imoveis novos que correspondem aos interesses dos seus clientes (ultimos 7 dias)
              </p>
            </CardHeader>
            <CardContent>
              {loadingAlertas ? (
                <p className="text-center text-muted-foreground py-4">Processando alertas...</p>
              ) : alertas.length === 0 ? (
                <p className="text-center text-muted-foreground py-4">
                  Nenhuma correspondencia encontrada no momento
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Cliente</TableHead>
                      <TableHead>E-mail</TableHead>
                      <TableHead>Imovel</TableHead>
                      <TableHead>Motivo</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {alertas.map((alerta, idx) => (
                      <TableRow key={`${alerta.cliente_id}-${alerta.imovel_id}-${idx}`}>
                        <TableCell className="font-medium">{alerta.cliente_nome}</TableCell>
                        <TableCell>{alerta.cliente_email || '-'}</TableCell>
                        <TableCell>{alerta.imovel_titulo}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{alerta.motivo}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Create Campaign Dialog */}
      <Dialog open={dialogAberto} onOpenChange={setDialogAberto}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Nova Campanha</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="camp-nome">Nome da Campanha</Label>
              <Input
                id="camp-nome"
                value={formNome}
                onChange={(e) => setFormNome(e.target.value)}
                placeholder="Ex: Lancamento novos apartamentos"
              />
            </div>
            <div className="space-y-2">
              <Label>Tipo</Label>
              <Select value={formTipo} onValueChange={(v: any) => setFormTipo(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="email">E-mail</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="alerta_imovel">Alerta de Imovel</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="camp-template">Template / Mensagem</Label>
              <Textarea
                id="camp-template"
                value={formTemplate}
                onChange={(e) => setFormTemplate(e.target.value)}
                placeholder="Escreva o conteudo da sua campanha..."
                rows={6}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="camp-origem">Filtro: Origem do Cliente</Label>
                <Input
                  id="camp-origem"
                  value={formFiltroOrigem}
                  onChange={(e) => setFormFiltroOrigem(e.target.value)}
                  placeholder="Ex: site, indicacao"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="camp-etapa">Filtro: Etapa do Funil</Label>
                <Input
                  id="camp-etapa"
                  value={formFiltroEtapa}
                  onChange={(e) => setFormFiltroEtapa(e.target.value)}
                  placeholder="Ex: qualificado"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogAberto(false)}>Cancelar</Button>
            <Button
              onClick={handleCreate}
              disabled={!formNome || !formTemplate || createMutation.isPending}
            >
              {createMutation.isPending ? 'Criando...' : 'Criar Campanha'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Campaign Detail Dialog */}
      <Dialog open={!!detalheCampanha} onOpenChange={() => setDetalheCampanha(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>{detalheCampanha?.nome}</DialogTitle>
          </DialogHeader>
          {detalheCampanha && (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-2">
                <Badge variant={STATUS_MAP[detalheCampanha.status]?.variant || 'secondary'}>
                  {STATUS_MAP[detalheCampanha.status]?.label || detalheCampanha.status}
                </Badge>
                <Badge variant="outline">
                  {TIPO_MAP[detalheCampanha.tipo]?.label || detalheCampanha.tipo}
                </Badge>
              </div>

              <div className="grid grid-cols-3 gap-4 text-center">
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <div className="text-2xl font-bold">{detalheCampanha.total_enviados}</div>
                    <div className="text-xs text-muted-foreground">Enviados</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <div className="text-2xl font-bold">{detalheCampanha.total_abertos}</div>
                    <div className="text-xs text-muted-foreground">Abertos</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <div className="text-2xl font-bold">{detalheCampanha.total_cliques}</div>
                    <div className="text-xs text-muted-foreground">Cliques</div>
                  </CardContent>
                </Card>
              </div>

              <div>
                <Label className="text-sm text-muted-foreground">Template</Label>
                <div className="mt-1 p-3 bg-muted rounded text-sm whitespace-pre-wrap">
                  {detalheCampanha.template}
                </div>
              </div>

              <div className="text-xs text-muted-foreground">
                Criada em {new Date(detalheCampanha.created_at).toLocaleString('pt-BR')}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Campanha</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza? Todos os envios desta campanha tambem serao excluidos.
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
