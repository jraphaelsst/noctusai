import { useState, useMemo } from 'react';
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
  Building2,
  Plus,
  Pencil,
  Trash2,
  MapPin,
  Users,
  Home,
  Loader2,
  BarChart3,
  Phone,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';
import {
  useFiliais,
  useCreateFilial,
  useUpdateFilial,
  useDeleteFilial,
  useConsolidadoFiliais,
  Filial,
} from '@/hooks/useFiliais';
import { useProfiles } from '@/hooks/useProfiles';

const ESTADOS_BR = [
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
  'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN',
  'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
];

interface FilialFormData {
  nome: string;
  codigo: string;
  endereco: string;
  cidade: string;
  estado: string;
  telefone: string;
  responsavel_id: string;
}

const emptyForm: FilialFormData = {
  nome: '',
  codigo: '',
  endereco: '',
  cidade: '',
  estado: '',
  telefone: '',
  responsavel_id: '',
};

export default function Filiais() {
  const [showInactive, setShowInactive] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingFilial, setEditingFilial] = useState<Filial | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formData, setFormData] = useState<FilialFormData>(emptyForm);
  const [showConsolidado, setShowConsolidado] = useState(false);

  const filiaisQuery = useFiliais(
    showInactive ? undefined : { is_active: true }
  );
  const { data: filiais } = filiaisQuery;
  const showFiliaisSkeleton = filiaisQuery.isPending && !filiaisQuery.data;
  const { data: consolidado } = useConsolidadoFiliais();
  const { data: profiles } = useProfiles();
  const { mutate: createFilial, isPending: isCreating } = useCreateFilial();
  const { mutate: updateFilial, isPending: isUpdating } = useUpdateFilial();
  const { mutate: deleteFilial, isPending: isDeleting } = useDeleteFilial();

  const isSaving = isCreating || isUpdating;

  const resetForm = () => {
    setEditingFilial(null);
    setFormData(emptyForm);
  };

  const handleOpenCreate = () => {
    resetForm();
    setDialogOpen(true);
  };

  const handleOpenEdit = (filial: Filial) => {
    setEditingFilial(filial);
    setFormData({
      nome: filial.nome,
      codigo: filial.codigo,
      endereco: filial.endereco || '',
      cidade: filial.cidade || '',
      estado: filial.estado || '',
      telefone: filial.telefone || '',
      responsavel_id: filial.responsavel_id || '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.nome.trim() || !formData.codigo.trim()) {
      return;
    }

    const payload = {
      nome: formData.nome.trim(),
      codigo: formData.codigo.trim(),
      endereco: formData.endereco || undefined,
      cidade: formData.cidade || undefined,
      estado: formData.estado || undefined,
      telefone: formData.telefone || undefined,
      responsavel_id: formData.responsavel_id || undefined,
    };

    if (editingFilial) {
      updateFilial(
        { id: editingFilial.id, ...payload },
        {
          onSuccess: () => {
            setDialogOpen(false);
            resetForm();
          },
        }
      );
    } else {
      createFilial(payload, {
        onSuccess: () => {
          setDialogOpen(false);
          resetForm();
        },
      });
    }
  };

  const handleToggleActive = (filial: Filial) => {
    updateFilial({ id: filial.id, is_active: !filial.is_active });
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteFilial(deleteId, {
        onSuccess: () => setDeleteId(null),
      });
    }
  };

  const getResponsavelNome = (id?: string | null) => {
    if (!id || !profiles) return '-';
    const profile = profiles.find((p: any) => p.id === id);
    return profile?.nome || id.slice(0, 8) + '...';
  };

  const filialList = filiais || [];

  // Consolidated stats
  const totalImoveis = consolidado?.totais?.imoveis ?? filialList.reduce((sum, f) => sum + (f.total_imoveis || 0), 0);
  const totalClientes = consolidado?.totais?.clientes ?? filialList.reduce((sum, f) => sum + (f.total_clientes || 0), 0);
  const totalFiliais = consolidado?.totais?.filiais ?? filialList.length;

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Filiais</h1>
          <p className="text-muted-foreground">Gestao de filiais e unidades</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowConsolidado(!showConsolidado)}>
            <BarChart3 className="h-4 w-4 mr-2" />
            Consolidado
          </Button>
          <Button variant="outline" onClick={() => setShowInactive(!showInactive)}>
            {showInactive ? (
              <>
                <ToggleRight className="h-4 w-4 mr-2" />
                Mostrando Todas
              </>
            ) : (
              <>
                <ToggleLeft className="h-4 w-4 mr-2" />
                Apenas Ativas
              </>
            )}
          </Button>
          <Button onClick={handleOpenCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Filial
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Filiais</CardTitle>
            <Building2 className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalFiliais}</div>
            <p className="text-xs text-muted-foreground">
              {filialList.filter((f) => f.is_active).length} ativas
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Imoveis Total</CardTitle>
            <Home className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalImoveis}</div>
            <p className="text-xs text-muted-foreground">em todas as filiais</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Clientes Total</CardTitle>
            <Users className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalClientes}</div>
            <p className="text-xs text-muted-foreground">em todas as filiais</p>
          </CardContent>
        </Card>
      </div>

      {/* Consolidated Dashboard */}
      {showConsolidado && filialList.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Comparativo entre Filiais
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Filial</TableHead>
                    <TableHead>Cidade/UF</TableHead>
                    <TableHead className="text-right">Imoveis</TableHead>
                    <TableHead className="text-right">Clientes</TableHead>
                    <TableHead>Responsavel</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filialList.map((filial) => (
                    <TableRow key={filial.id}>
                      <TableCell className="font-medium">
                        <div>
                          <p>{filial.nome}</p>
                          <p className="text-xs text-muted-foreground font-mono">{filial.codigo}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        {filial.cidade && filial.estado
                          ? `${filial.cidade}/${filial.estado}`
                          : filial.cidade || filial.estado || '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="font-semibold">{filial.total_imoveis || 0}</span>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="font-semibold">{filial.total_clientes || 0}</span>
                      </TableCell>
                      <TableCell>{getResponsavelNome(filial.responsavel_id)}</TableCell>
                      <TableCell>
                        <Badge variant={filial.is_active ? 'default' : 'secondary'}>
                          {filial.is_active ? 'Ativa' : 'Inativa'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                  {/* Totals Row */}
                  <TableRow className="font-bold bg-muted/50">
                    <TableCell>Total</TableCell>
                    <TableCell>-</TableCell>
                    <TableCell className="text-right">{totalImoveis}</TableCell>
                    <TableCell className="text-right">{totalClientes}</TableCell>
                    <TableCell>-</TableCell>
                    <TableCell>-</TableCell>
                  </TableRow>
                </TableBody>
              </Table>

              {/* Visual comparison bars */}
              {filialList.length > 1 && (
                <div className="mt-6 space-y-4">
                  <h4 className="text-sm font-medium text-muted-foreground">Distribuicao de Imoveis</h4>
                  {filialList
                    .filter((f) => f.is_active)
                    .map((filial) => {
                      const maxImoveis = Math.max(...filialList.map((f) => f.total_imoveis || 0), 1);
                      const percentage = ((filial.total_imoveis || 0) / maxImoveis) * 100;
                      return (
                        <div key={filial.id} className="space-y-1">
                          <div className="flex justify-between text-sm">
                            <span>{filial.nome}</span>
                            <span className="font-medium">{filial.total_imoveis || 0}</span>
                          </div>
                          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary rounded-full transition-all"
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}

                  <h4 className="text-sm font-medium text-muted-foreground mt-6">Distribuicao de Clientes</h4>
                  {filialList
                    .filter((f) => f.is_active)
                    .map((filial) => {
                      const maxClientes = Math.max(...filialList.map((f) => f.total_clientes || 0), 1);
                      const percentage = ((filial.total_clientes || 0) / maxClientes) * 100;
                      return (
                        <div key={filial.id} className="space-y-1">
                          <div className="flex justify-between text-sm">
                            <span>{filial.nome}</span>
                            <span className="font-medium">{filial.total_clientes || 0}</span>
                          </div>
                          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-green-500 rounded-full transition-all"
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Branch Cards */}
      {showFiliaisSkeleton ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : filialList.length === 0 ? (
        <Card className="py-12">
          <CardContent className="text-center">
            <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg text-muted-foreground">Nenhuma filial cadastrada</p>
            <p className="text-sm text-muted-foreground mb-4">
              Crie sua primeira filial para comecar.
            </p>
            <Button onClick={handleOpenCreate}>
              <Plus className="h-4 w-4 mr-2" />
              Nova Filial
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filialList.map((filial) => (
            <Card
              key={filial.id}
              className={`relative transition-shadow hover:shadow-md ${
                !filial.is_active ? 'opacity-60' : ''
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <CardTitle className="text-lg truncate">{filial.nome}</CardTitle>
                    <p className="text-sm text-muted-foreground font-mono">{filial.codigo}</p>
                  </div>
                  <Badge variant={filial.is_active ? 'default' : 'secondary'}>
                    {filial.is_active ? 'Ativa' : 'Inativa'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Location */}
                {(filial.cidade || filial.estado) && (
                  <div className="flex items-center gap-2 text-sm">
                    <MapPin className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span>
                      {[filial.endereco, filial.cidade, filial.estado]
                        .filter(Boolean)
                        .join(', ')}
                    </span>
                  </div>
                )}

                {/* Phone */}
                {filial.telefone && (
                  <div className="flex items-center gap-2 text-sm">
                    <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span>{filial.telefone}</span>
                  </div>
                )}

                {/* Responsavel */}
                {filial.responsavel_id && (
                  <div className="flex items-center gap-2 text-sm">
                    <Users className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span>{getResponsavelNome(filial.responsavel_id)}</span>
                  </div>
                )}

                {/* Stats */}
                <div className="flex gap-4 pt-2 border-t">
                  <div className="flex items-center gap-1.5">
                    <Home className="h-4 w-4 text-blue-600" />
                    <span className="text-sm font-semibold">{filial.total_imoveis || 0}</span>
                    <span className="text-xs text-muted-foreground">imoveis</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Users className="h-4 w-4 text-green-600" />
                    <span className="text-sm font-semibold">{filial.total_clientes || 0}</span>
                    <span className="text-xs text-muted-foreground">clientes</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2 border-t">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="flex-1"
                    onClick={() => handleOpenEdit(filial)}
                  >
                    <Pencil className="h-4 w-4 mr-1" />
                    Editar
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleToggleActive(filial)}
                  >
                    {filial.is_active ? (
                      <ToggleRight className="h-4 w-4" />
                    ) : (
                      <ToggleLeft className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => setDeleteId(filial.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingFilial ? 'Editar Filial' : 'Nova Filial'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="nome">Nome *</Label>
                <Input
                  id="nome"
                  value={formData.nome}
                  onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                  placeholder="Filial Centro"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="codigo">Codigo *</Label>
                <Input
                  id="codigo"
                  value={formData.codigo}
                  onChange={(e) => setFormData({ ...formData, codigo: e.target.value.toUpperCase() })}
                  placeholder="FIL-001"
                  className="font-mono"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="endereco">Endereco</Label>
              <Input
                id="endereco"
                value={formData.endereco}
                onChange={(e) => setFormData({ ...formData, endereco: e.target.value })}
                placeholder="Rua, numero, bairro"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cidade">Cidade</Label>
                <Input
                  id="cidade"
                  value={formData.cidade}
                  onChange={(e) => setFormData({ ...formData, cidade: e.target.value })}
                  placeholder="Sao Paulo"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="estado">Estado</Label>
                <Select
                  value={formData.estado}
                  onValueChange={(v) => setFormData({ ...formData, estado: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ESTADOS_BR.map((uf) => (
                      <SelectItem key={uf} value={uf}>{uf}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="telefone">Telefone</Label>
                <Input
                  id="telefone"
                  value={formData.telefone}
                  onChange={(e) => setFormData({ ...formData, telefone: e.target.value })}
                  placeholder="(11) 99999-9999"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="responsavel">Responsavel</Label>
                <Select
                  value={formData.responsavel_id}
                  onValueChange={(v) => setFormData({ ...formData, responsavel_id: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione..." />
                  </SelectTrigger>
                  <SelectContent>
                    {profiles && profiles.length > 0 ? (
                      profiles.map((profile: any) => (
                        <SelectItem key={profile.id} value={profile.id}>
                          {profile.nome || profile.email || profile.id.slice(0, 8)}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="none" disabled>
                        Nenhum usuario encontrado
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isSaving || !formData.nome.trim() || !formData.codigo.trim()}
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Salvando...
                </>
              ) : editingFilial ? (
                'Salvar'
              ) : (
                'Criar Filial'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Filial</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta filial? Esta acao e irreversivel e todos os dados
              associados serao permanentemente removidos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive hover:bg-destructive/90"
              disabled={isDeleting}
            >
              {isDeleting ? 'Excluindo...' : 'Excluir'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
