import { Input } from '@noctusai/seed/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { Switch } from '@noctusai/seed/components/ui/switch';
import { Label } from '@noctusai/seed/components/ui/label';
import { Button } from '@noctusai/seed/components/ui/button';
import { X, Plus } from 'lucide-react';
import { useFunilFiltrosStore } from '@/store/funilFiltrosStore';
import { useProfiles } from '@/hooks/useProfiles';
import { useIsAdminOrCoordenador } from '@/hooks/useIsAdminOrCoordenador';
import { funilPipeline } from '@/lib/pipelines';
import { EtapaFunil } from '@/types/clientes';

interface FiltrosFunilProps {
  onNovoCliente?: () => void;
}

export function FiltrosFunil({ onNovoCliente }: FiltrosFunilProps) {
  const {
    busca,
    responsavelId,
    origem,
    etapa,
    incluirArquivados,
    setBusca,
    setResponsavelId,
    setOrigem,
    setEtapa,
    setIncluirArquivados,
    limparFiltros,
  } = useFunilFiltrosStore();

  const { data: profiles } = useProfiles();
  const { isAdminOrCoordenador } = useIsAdminOrCoordenador();

  const origens = ['Indicação', 'Site', 'Redes Sociais', 'Telefone', 'Email', 'Evento', 'Outros'];
  // Stages come from the DB, not a hardcoded map — the filter must offer
  // exactly the columns the board renders, including ones the user added.
  const { data: etapasFunil } = funilPipeline.useStages();
  const etapas = [...(etapasFunil ?? [])]
    .sort((a, b) => a.posicao - b.posicao)
    .map((e) => ({ value: e.id, label: e.label }));

  return (
    <div className="flex flex-col gap-4 mb-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Funil de Vendas</h1>
        {onNovoCliente && (
          <Button onClick={onNovoCliente}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Cliente
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <Label htmlFor="busca">Buscar</Label>
          <Input
            id="busca"
            placeholder="Nome, email ou telefone..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>

        {isAdminOrCoordenador && (
          <div className="w-48">
            <Label htmlFor="responsavel">Responsável</Label>
            <Select value={responsavelId} onValueChange={setResponsavelId}>
              <SelectTrigger id="responsavel">
                <SelectValue placeholder="Selecione o responsável" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                {profiles?.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id}>
                    {profile.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="w-48">
          <Label htmlFor="etapa">Etapa</Label>
          <Select value={etapa} onValueChange={setEtapa}>
            <SelectTrigger id="etapa">
              <SelectValue placeholder="Selecione a etapa" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              {etapas.map((e) => (
                <SelectItem key={e.value} value={e.value}>
                  {e.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-48">
          <Label htmlFor="origem">Origem</Label>
          <Select value={origem} onValueChange={setOrigem}>
            <SelectTrigger id="origem">
              <SelectValue placeholder="Selecione a origem" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              {origens.map((o) => (
                <SelectItem key={o} value={o}>
                  {o}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="arquivados"
            checked={incluirArquivados}
            onCheckedChange={setIncluirArquivados}
          />
          <Label htmlFor="arquivados">Incluir arquivados</Label>
        </div>

        <Button variant="outline" onClick={limparFiltros}>
          <X className="w-4 h-4 mr-2" />
          Limpar
        </Button>
      </div>
    </div>
  );
}
