import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Card } from '@noctusai/seed/components/ui/card';
import { Plus, ExternalLink, Archive, Trash2 } from 'lucide-react';
import { useClientes, useToggleArquivarCliente, useDeleteCliente } from '@/hooks/useClientes';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { NovoClienteDialog } from '@/components/clientes/NovoClienteDialog';
import { ETAPAS_CONFIG } from '@/lib/etapasConfig';
import { formatCurrency } from '@/lib/utils';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { FiltrosFunil } from '@/components/clientes/FiltrosFunil';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
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

export default function Clientes() {
  const navigate = useNavigate();
  const [novoClienteOpen, setNovoClienteOpen] = useState(false);
  const [deleteClienteId, setDeleteClienteId] = useState<string | null>(null);

  const filtrosStore = useFunilFiltrosStore();
  const { data: clientes, isLoading } = useClientes({
    ...filtrosStore,
    etapa: filtrosStore.etapa === 'todas' ? undefined : filtrosStore.etapa,
  });
  const { mutate: toggleArquivar } = useToggleArquivarCliente();
  const { mutate: deleteCliente } = useDeleteCliente();

  const handleDelete = () => {
    if (deleteClienteId) {
      deleteCliente(deleteClienteId);
      setDeleteClienteId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold">Clientes</h1>
        <Button onClick={() => setNovoClienteOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Novo Cliente
        </Button>
      </div>

      <FiltrosFunil />

      <div className="grid gap-4">
        {isLoading ? (
          <CardListSkeleton count={4} />
        ) : clientes && clientes.length > 0 ? (
          clientes.map((cliente) => {
            const etapaConfig = ETAPAS_CONFIG[cliente.etapa_atual];
            const tempoRelativo = cliente.updated_at
              ? formatDistanceToNow(new Date(cliente.updated_at), {
                  addSuffix: true,
                  locale: ptBR,
                })
              : null;

            return (
              <Card key={cliente.id} className="p-4 hover:shadow-md transition-shadow">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div className="flex-1 min-w-0 w-full sm:w-auto">
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
                      <h3 className="font-semibold text-lg truncate">{cliente.nome}</h3>
                      <Badge className={etapaConfig.bgColor}>{etapaConfig.label}</Badge>
                      {cliente.arquivado && <Badge variant="secondary">Arquivado</Badge>}
                    </div>

                    <div className="flex flex-wrap gap-2 mb-2">
                      {cliente.email && (
                        <span className="text-sm text-muted-foreground">{cliente.email}</span>
                      )}
                      {cliente.telefone && (
                        <span className="text-sm text-muted-foreground">{cliente.telefone}</span>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{cliente.probabilidade}%</Badge>
                      <Badge variant="outline">
                        {formatCurrency(Number(cliente.valor_estimado))}
                      </Badge>
                      {cliente.origem && <Badge variant="outline">{cliente.origem}</Badge>}
                      {cliente.usuario && (
                        <Badge variant="outline">{cliente.usuario.nome}</Badge>
                      )}
                    </div>

                    {tempoRelativo && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Atualizado {tempoRelativo}
                      </p>
                    )}
                  </div>

                  <div className="flex gap-2 w-full sm:w-auto sm:ml-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1 sm:flex-none"
                      onClick={() => navigate(`/clientes/${cliente.id}`)}
                    >
                      <ExternalLink className="w-4 h-4 sm:mr-2" />
                      <span className="hidden sm:inline">Ver Detalhes</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleArquivar(cliente.id)}
                    >
                      <Archive className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setDeleteClienteId(cliente.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })
        ) : (
          <Card className="p-8 text-center text-muted-foreground">
            Nenhum cliente encontrado
          </Card>
        )}
      </div>

      <NovoClienteDialog open={novoClienteOpen} onOpenChange={setNovoClienteOpen} />

      <AlertDialog open={!!deleteClienteId} onOpenChange={() => setDeleteClienteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Cliente</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este cliente? Esta ação é irreversível e todos os dados associados, incluindo histórico de atividades, serão permanentemente removidos.
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
