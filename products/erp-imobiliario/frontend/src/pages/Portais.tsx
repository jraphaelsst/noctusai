import { useState } from 'react';
import {
  usePortaisFeeds,
  useImoveisPortal,
  useTogglePortal,
  usePortalFeedUrl,
} from '@/hooks/usePortais';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { CardGridSkeleton, TableSkeleton } from '@/components/ui/page-skeleton';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Switch } from '@noctusai/seed/components/ui/switch';
import { Input } from '@noctusai/seed/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Globe,
  Copy,
  Check,
  Rss,
  Search,
  HomeIcon,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatCurrency } from '@/lib/utils';

const portalColors: Record<string, string> = {
  zap: 'bg-purple-100 text-purple-800',
  olx: 'bg-orange-100 text-orange-800',
  vivareal: 'bg-blue-100 text-blue-800',
};

export default function Portais() {
  const feedsQuery = usePortaisFeeds();
  const { data: feeds = [] } = feedsQuery;
  const showFeedsSkeleton = feedsQuery.isPending && !feedsQuery.data;
  const [filtroPortal, setFiltroPortal] = useState<string>('todos');
  const [busca, setBusca] = useState('');
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  const prontoFilter = filtroPortal === 'prontos' ? true : filtroPortal === 'nao_prontos' ? false : undefined;
  const imoveisQuery = useImoveisPortal(prontoFilter);
  const { data: imoveis = [] } = imoveisQuery;
  const showImoveisPortalSkeleton = imoveisQuery.isPending && !imoveisQuery.data;
  const toggleMutation = useTogglePortal();

  const zapUrl = usePortalFeedUrl('zap');
  const olxUrl = usePortalFeedUrl('olx');
  const vivarealUrl = usePortalFeedUrl('vivareal');

  const feedUrls: Record<string, string> = { zap: zapUrl, olx: olxUrl, vivareal: vivarealUrl };

  const handleCopyUrl = async (portal: string) => {
    const url = feedUrls[portal];
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(portal);
      toast.success('URL copiada!');
      setTimeout(() => setCopiedUrl(null), 2000);
    } catch {
      toast.error('Erro ao copiar URL');
    }
  };

  const handleToggle = (imovelId: string, currentValue: boolean) => {
    toggleMutation.mutate({ imovelId, prontoParaPortais: !currentValue });
  };

  const imoveisFiltrados = imoveis.filter((im) => {
    if (!busca) return true;
    const q = busca.toLowerCase();
    return (
      im.titulo_anuncio?.toLowerCase().includes(q) ||
      im.cidade?.toLowerCase().includes(q) ||
      im.bairro?.toLowerCase().includes(q) ||
      im.tipo_imovel?.toLowerCase().includes(q) ||
      im.id.toLowerCase().includes(q)
    );
  });

  const totalProntos = imoveis.filter((im) => im.pronto_para_portais).length;

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Portais</h1>
        <p className="text-muted-foreground">
          Gerencie feeds XML para portais imobiliarios e controle a publicacao dos seus imoveis
        </p>
      </div>

      {/* Feed Cards */}
      <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
        {showFeedsSkeleton ? (
          <CardGridSkeleton count={3} />
        ) : (
          feeds.map((feed) => (
            <Card key={feed.portal}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Rss className="h-5 w-5" />
                    {feed.nome}
                  </CardTitle>
                  <Badge className={portalColors[feed.portal] || ''}>
                    {feed.imoveis_prontos} imoveis
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{feed.descricao}</p>
                <p className="text-xs text-muted-foreground">Formato: {feed.formato}</p>

                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={feedUrls[feed.portal] || feed.url}
                    className="text-xs font-mono"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopyUrl(feed.portal)}
                    title="Copiar URL"
                  >
                    {copiedUrl === feed.portal ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => window.open(feedUrls[feed.portal], '_blank')}
                    title="Abrir feed"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Summary */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Imoveis nos Portais ({totalProntos} prontos de {imoveis.length})
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                placeholder="Buscar por titulo, cidade, bairro..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={filtroPortal} onValueChange={setFiltroPortal}>
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                <SelectItem value="prontos">Prontos para portais</SelectItem>
                <SelectItem value="nao_prontos">Nao publicados</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Table */}
          {showImoveisPortalSkeleton ? (
            <TableSkeleton rows={4} />
          ) : imoveisFiltrados.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <HomeIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhum imovel encontrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Imovel</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Localizacao</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Fotos</TableHead>
                  <TableHead>SEO</TableHead>
                  <TableHead className="text-center">Portal Ativo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {imoveisFiltrados.map((imovel) => (
                  <TableRow key={imovel.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium truncate max-w-[200px]">
                          {imovel.titulo_anuncio || 'Sem titulo'}
                        </p>
                        <p className="text-xs text-muted-foreground">{imovel.id.slice(0, 8)}...</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize">
                        {imovel.tipo_imovel || 'N/A'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">
                        {[imovel.bairro, imovel.cidade, imovel.estado].filter(Boolean).join(', ') || '-'}
                      </span>
                    </TableCell>
                    <TableCell className="font-medium">{formatCurrency(imovel.valor)}</TableCell>
                    <TableCell>
                      <Badge variant={imovel.fotos && imovel.fotos.length > 0 ? 'default' : 'secondary'}>
                        {imovel.fotos?.length || 0}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {imovel.descricao_seo ? (
                        <Badge variant="default">Sim</Badge>
                      ) : (
                        <Badge variant="secondary">Nao</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={imovel.pronto_para_portais}
                        onCheckedChange={() => handleToggle(imovel.id, imovel.pronto_para_portais)}
                        disabled={toggleMutation.isPending}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
