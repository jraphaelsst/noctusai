import { useState } from 'react';
import { useCondominios, useDeleteCondominio } from '@/hooks/useCondominios';
import { NovoCondominioDialog } from '@/components/condominios/NovoCondominioDialog';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Search, Plus, Building2, MapPin, Phone, Users, Trash2,
  Waves, Dumbbell, PartyPopper, TreePine, Flame, ShieldCheck
} from 'lucide-react';
import { formatCurrency } from '@/lib/utils';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import { CardGridSkeleton } from '@/components/ui/page-skeleton';

export default function Condominios() {
  const condominiosQuery = useCondominios();
  const { data: condominios = [] } = condominiosQuery;
  const showCondominiosSkeleton = condominiosQuery.isPending && !condominiosQuery.data;
  const deleteMutation = useDeleteCondominio();
  const [busca, setBusca] = useState('');
  const [dialogAberto, setDialogAberto] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const filtrados = condominios.filter((c) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return (
      c.nome.toLowerCase().includes(q) ||
      c.cidade?.toLowerCase().includes(q) ||
      c.bairro?.toLowerCase().includes(q) ||
      c.administradora?.toLowerCase().includes(q)
    );
  });

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      setDeleteId(null);
    }
  };

  const amenityIcons = [
    { key: 'possui_portaria', icon: ShieldCheck, label: 'Portaria' },
    { key: 'possui_piscina', icon: Waves, label: 'Piscina' },
    { key: 'possui_academia', icon: Dumbbell, label: 'Academia' },
    { key: 'possui_salao_festas', icon: PartyPopper, label: 'Salão' },
    { key: 'possui_playground', icon: TreePine, label: 'Playground' },
    { key: 'possui_churrasqueira', icon: Flame, label: 'Churrasqueira' },
  ];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Condomínios</h1>
          <p className="text-muted-foreground">Gerencie os condomínios cadastrados</p>
        </div>
        <Button onClick={() => setDialogAberto(true)}>
          <Plus className="h-4 w-4 mr-2" />Novo Condomínio
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por nome, cidade, bairro..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="pl-10"
            />
          </div>
        </CardContent>
      </Card>

      {showCondominiosSkeleton ? (
        <CardGridSkeleton count={6} />
      ) : filtrados.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhum condomínio encontrado</p>
            <p className="text-sm mt-1">Cadastre um condomínio para vinculá-lo aos seus imóveis</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtrados.map((cond) => (
            <Card key={cond.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-primary" />
                    <h3 className="font-semibold text-lg">{cond.nome}</h3>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setDeleteId(cond.id)}>
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </div>

                {(cond.cidade || cond.bairro) && (
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <MapPin className="h-3 w-3" />
                    {[cond.bairro, cond.cidade, cond.estado].filter(Boolean).join(', ')}
                  </div>
                )}

                {cond.valor_condominio && cond.valor_condominio > 0 && (
                  <div className="text-lg font-bold text-primary">
                    {formatCurrency(cond.valor_condominio)}/mês
                  </div>
                )}

                <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                  {cond.torres && <div><strong>Torres:</strong> {cond.torres}</div>}
                  {cond.total_unidades && <div><strong>Unidades:</strong> {cond.total_unidades}</div>}
                  {cond.unidades_por_andar && <div><strong>P/ andar:</strong> {cond.unidades_por_andar}</div>}
                </div>

                {cond.sindico && (
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Users className="h-3 w-3" />
                    <span>{cond.sindico}</span>
                    {cond.telefone_sindico && (
                      <>
                        <Phone className="h-3 w-3 ml-2" />
                        <span>{cond.telefone_sindico}</span>
                      </>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap gap-1.5">
                  {amenityIcons.map(({ key, icon: Icon, label }) =>
                    (cond as any)[key] ? (
                      <Badge key={key} variant="secondary" className="text-xs gap-1">
                        <Icon className="h-3 w-3" />{label}
                      </Badge>
                    ) : null
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <NovoCondominioDialog open={dialogAberto} onOpenChange={setDialogAberto} />

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Condomínio</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza? Imóveis vinculados a este condomínio perderão a referência.
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
