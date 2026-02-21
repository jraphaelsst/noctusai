import { useState } from 'react';
import { useImoveis } from '@/hooks/useImoveis';
import { useRecalcularMatches } from '@/hooks/useMatches';
import { useCondominios } from '@/hooks/useCondominios';
import { NovoImovelDialog } from '@/components/imoveis/NovoImovelDialog';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Search, Plus, HomeIcon, Sparkles, Building2, MapPin, BedDouble, Car } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

export default function Imoveis() {
  const { data: imoveis = [], isLoading } = useImoveis();
  const { data: condominios = [] } = useCondominios();
  const recalcularMutation = useRecalcularMatches();
  const [busca, setBusca] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('todos');
  const [dialogAberto, setDialogAberto] = useState(false);

  const imoveisFiltrados = imoveis.filter((imovel) => {
    const matchBusca = !busca ||
      imovel.id.toLowerCase().includes(busca.toLowerCase()) ||
      imovel.cidade?.toLowerCase().includes(busca.toLowerCase()) ||
      imovel.bairro?.toLowerCase().includes(busca.toLowerCase()) ||
      imovel.titulo_anuncio?.toLowerCase().includes(busca.toLowerCase()) ||
      imovel.condominio_nome?.toLowerCase().includes(busca.toLowerCase());
    const matchTipo = filtroTipo === 'todos' || imovel.tipo === filtroTipo;
    return matchBusca && matchTipo;
  });

  const handleGerarMatch = async (imovelId: string) => {
    await recalcularMutation.mutateAsync({ imovel_id: imovelId });
  };

  // Find condominio name by ID
  const getCondominioNome = (imovel: any) => {
    if (imovel.condominio_nome) return imovel.condominio_nome;
    if (imovel.condominio_id) {
      const cond = condominios.find(c => c.id === imovel.condominio_id);
      return cond?.nome || null;
    }
    return null;
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Imóveis</h1>
          <p className="text-muted-foreground">Gerencie seus imóveis e busque matches de permuta</p>
        </div>
        <Button onClick={() => setDialogAberto(true)}>
          <Plus className="h-4 w-4 mr-2" />Novo Imóvel
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input placeholder="Buscar por cidade, bairro, título..." value={busca} onChange={(e) => setBusca(e.target.value)} className="pl-10" />
            </div>
            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[200px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os tipos</SelectItem>
                <SelectItem value="casa">Casa</SelectItem>
                <SelectItem value="apartamento">Apartamento</SelectItem>
                <SelectItem value="terreno">Terreno</SelectItem>
                <SelectItem value="comercial">Comercial</SelectItem>
                <SelectItem value="rural">Rural</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Carregando...</CardContent></Card>
      ) : imoveisFiltrados.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <HomeIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhum imóvel encontrado</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {imoveisFiltrados.map((imovel) => {
            const condNome = getCondominioNome(imovel);

            return (
              <Card key={imovel.id} className="hover:shadow-md transition-shadow">
                <CardContent className="pt-6 space-y-3">
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <HomeIcon className="h-5 w-5 text-primary" />
                      <span className="font-semibold capitalize">{imovel.tipo}</span>
                    </div>
                    <div className="flex gap-1">
                      <Badge>{imovel.finalidade}</Badge>
                      {imovel.aceita_permutas && <Badge variant="secondary">Permuta</Badge>}
                    </div>
                  </div>

                  {/* Location */}
                  {(imovel.cidade || imovel.bairro) && (
                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                      <MapPin className="h-3 w-3" />
                      {[imovel.bairro, imovel.cidade, imovel.estado].filter(Boolean).join(', ')}
                    </div>
                  )}

                  {/* Condominio */}
                  {condNome && (
                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                      <Building2 className="h-3 w-3" />
                      <span>{condNome}</span>
                    </div>
                  )}

                  {/* Specs */}
                  <div className="flex gap-3 text-sm text-muted-foreground">
                    {imovel.quartos && (
                      <span className="flex items-center gap-1"><BedDouble className="h-3 w-3" />{imovel.quartos}q</span>
                    )}
                    {imovel.vagas && (
                      <span className="flex items-center gap-1"><Car className="h-3 w-3" />{imovel.vagas}v</span>
                    )}
                    {(imovel.area_total || imovel.area_privativa) && (
                      <span>{imovel.area_total || imovel.area_privativa}m²</span>
                    )}
                  </div>

                  {/* Price */}
                  <p className="text-lg font-bold text-primary">{formatCurrency(imovel.preco_pedido)}</p>

                  {/* Title */}
                  {imovel.titulo_anuncio && (
                    <p className="text-sm text-muted-foreground truncate">{imovel.titulo_anuncio}</p>
                  )}

                  {/* Match button */}
                  {imovel.aceita_permutas && (
                    <Button className="w-full" variant="outline" onClick={() => handleGerarMatch(imovel.id)} disabled={recalcularMutation.isPending}>
                      <Sparkles className="h-4 w-4 mr-2" />Gerar Matches
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <NovoImovelDialog open={dialogAberto} onOpenChange={setDialogAberto} />
    </div>
  );
}
