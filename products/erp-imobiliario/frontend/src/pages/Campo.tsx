import { useState, useCallback, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  MapPin,
  Navigation,
  Clock,
  Camera,
  CheckCircle2,
  Loader2,
  ClipboardCheck,
  Eye,
  Home,
  AlertTriangle,
  RefreshCw,
  Download,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatDate } from '@/lib/utils';
import {
  useCheckins,
  useCreateCheckin,
  useVistoriaRapida,
  useImoveisProximos,
  useSyncCampo,
  useOfflineData,
  Checkin,
} from '@/hooks/useCampo';

type TipoCheckin = 'visita' | 'vistoria' | 'captacao' | 'reuniao';

const TIPO_CONFIG: Record<TipoCheckin, { label: string; className: string; icon: string }> = {
  visita: { label: 'Visita', className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200', icon: 'eye' },
  vistoria: { label: 'Vistoria', className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200', icon: 'clipboard' },
  captacao: { label: 'Captacao', className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', icon: 'home' },
  reuniao: { label: 'Reuniao', className: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200', icon: 'users' },
};

const CHECKLIST_ITEMS = [
  { key: 'estrutura', label: 'Estrutura' },
  { key: 'pintura', label: 'Pintura' },
  { key: 'eletrica', label: 'Eletrica' },
  { key: 'hidraulica', label: 'Hidraulica' },
  { key: 'piso', label: 'Piso' },
  { key: 'portas_janelas', label: 'Portas/Janelas' },
  { key: 'cozinha', label: 'Cozinha' },
  { key: 'banheiro', label: 'Banheiro' },
  { key: 'area_externa', label: 'Area Externa' },
  { key: 'limpeza', label: 'Limpeza' },
];

export default function Campo() {
  const [currentPosition, setCurrentPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [isGettingLocation, setIsGettingLocation] = useState(false);
  const [checkinTipo, setCheckinTipo] = useState<TipoCheckin>('visita');
  const [checkinImovelId, setCheckinImovelId] = useState('');
  const [checkinNotes, setCheckinNotes] = useState('');
  const [checkinSuccess, setCheckinSuccess] = useState(false);

  // Vistoria state
  const [vistoriaDialogOpen, setVistoriaDialogOpen] = useState(false);
  const [vistoriaImovelId, setVistoriaImovelId] = useState('');
  const [vistoriaEstado, setVistoriaEstado] = useState<'bom' | 'regular' | 'ruim' | 'critico'>('bom');
  const [vistoriaChecklist, setVistoriaChecklist] = useState<Record<string, boolean>>({});
  const [vistoriaObs, setVistoriaObs] = useState('');

  const { data: checkins, isLoading: isLoadingCheckins } = useCheckins();
  const { mutate: createCheckin, isPending: isCreatingCheckin } = useCreateCheckin();
  const { mutate: criarVistoria, isPending: isCriandoVistoria } = useVistoriaRapida();
  const { data: imoveisProximos } = useImoveisProximos(
    currentPosition?.lat,
    currentPosition?.lng,
    5
  );
  const { mutate: syncCampo, isPending: isSyncing } = useSyncCampo();
  const { data: offlineData, refetch: refetchOffline, isFetching: isDownloadingOffline } = useOfflineData();

  const [lastSyncTime, setLastSyncTime] = useState<string | null>(() =>
    localStorage.getItem('campo_last_sync')
  );
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  // Track online/offline status
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const handleSync = () => {
    const pendingCheckins = JSON.parse(localStorage.getItem('campo_pending_checkins') || '[]');
    const pendingVistorias = JSON.parse(localStorage.getItem('campo_pending_vistorias') || '[]');
    syncCampo(
      { checkins: pendingCheckins, vistorias: pendingVistorias },
      {
        onSuccess: () => {
          localStorage.removeItem('campo_pending_checkins');
          localStorage.removeItem('campo_pending_vistorias');
          const now = new Date().toISOString();
          localStorage.setItem('campo_last_sync', now);
          setLastSyncTime(now);
        },
      }
    );
  };

  const handleDownloadOffline = async () => {
    const { data } = await refetchOffline();
    if (data) {
      localStorage.setItem('campo_offline_data', JSON.stringify(data));
      const now = new Date().toISOString();
      localStorage.setItem('campo_offline_downloaded_at', now);
      toast.success('Dados offline salvos com sucesso!');
    }
  };

  const getLocation = useCallback((): Promise<{ lat: number; lng: number }> => {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Geolocalizacao nao suportada pelo navegador'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (position) => {
          resolve({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          });
        },
        (error) => {
          let message = 'Erro ao obter localizacao';
          switch (error.code) {
            case error.PERMISSION_DENIED:
              message = 'Permissao de localizacao negada. Habilite nas configuracoes do navegador.';
              break;
            case error.POSITION_UNAVAILABLE:
              message = 'Localizacao indisponivel.';
              break;
            case error.TIMEOUT:
              message = 'Tempo esgotado ao obter localizacao.';
              break;
          }
          reject(new Error(message));
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 0,
        }
      );
    });
  }, []);

  const handleGetLocation = async () => {
    setIsGettingLocation(true);
    try {
      const pos = await getLocation();
      setCurrentPosition(pos);
      toast.success('Localizacao obtida!');
    } catch (error: any) {
      toast.error(error.message || 'Erro ao obter localizacao');
    } finally {
      setIsGettingLocation(false);
    }
  };

  const handleCheckin = async () => {
    if (!currentPosition) {
      toast.error('Obtenha sua localizacao primeiro.');
      return;
    }

    createCheckin(
      {
        latitude: currentPosition.lat,
        longitude: currentPosition.lng,
        tipo: checkinTipo,
        imovel_id: checkinImovelId || undefined,
        observacoes: checkinNotes || undefined,
      },
      {
        onSuccess: () => {
          setCheckinSuccess(true);
          setCheckinNotes('');
          setCheckinImovelId('');
          setTimeout(() => setCheckinSuccess(false), 3000);
        },
      }
    );
  };

  const handleVistoriaSubmit = () => {
    if (!currentPosition) {
      toast.error('Obtenha sua localizacao primeiro.');
      return;
    }
    if (!vistoriaImovelId) {
      toast.error('Informe o ID do imovel.');
      return;
    }

    criarVistoria(
      {
        imovel_id: vistoriaImovelId,
        latitude: currentPosition.lat,
        longitude: currentPosition.lng,
        estado_geral: vistoriaEstado,
        itens_checklist: vistoriaChecklist,
        observacoes: vistoriaObs || undefined,
      },
      {
        onSuccess: () => {
          setVistoriaDialogOpen(false);
          setVistoriaImovelId('');
          setVistoriaEstado('bom');
          setVistoriaChecklist({});
          setVistoriaObs('');
        },
      }
    );
  };

  const recentCheckins = (checkins || []).slice(0, 20);

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Campo</h1>
          <p className="text-muted-foreground">Check-in, vistorias e atividades externas</p>
        </div>
        <Button variant="outline" onClick={() => setVistoriaDialogOpen(true)}>
          <ClipboardCheck className="h-4 w-4 mr-2" />
          Vistoria Rapida
        </Button>
      </div>

      {/* Sync Toolbar */}
      <Card className="border-dashed">
        <CardContent className="py-3 px-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              {isOnline ? (
                <Badge variant="outline" className="bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300 border-green-200">
                  <Wifi className="h-3 w-3 mr-1" />
                  Online
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300 border-red-200">
                  <WifiOff className="h-3 w-3 mr-1" />
                  Offline
                </Badge>
              )}
              {lastSyncTime && (
                <span className="text-xs text-muted-foreground">
                  Ultima sinc.: {formatDate(lastSyncTime, true)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSync}
                disabled={isSyncing || !isOnline}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isSyncing ? 'animate-spin' : ''}`} />
                {isSyncing ? 'Sincronizando...' : 'Sincronizar Dados'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadOffline}
                disabled={isDownloadingOffline || !isOnline}
              >
                <Download className={`h-4 w-4 mr-2 ${isDownloadingOffline ? 'animate-bounce' : ''}`} />
                {isDownloadingOffline ? 'Baixando...' : 'Baixar Dados Offline'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Check-in Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Check-in Card */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Check-in
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* GPS Button */}
            <div className="flex flex-col items-center space-y-4">
              <Button
                size="lg"
                className={`w-full max-w-sm h-20 text-lg font-semibold transition-all ${
                  checkinSuccess
                    ? 'bg-green-600 hover:bg-green-700'
                    : currentPosition
                      ? 'bg-primary hover:bg-primary/90'
                      : ''
                }`}
                onClick={currentPosition ? handleCheckin : handleGetLocation}
                disabled={isGettingLocation || isCreatingCheckin}
              >
                {isGettingLocation ? (
                  <>
                    <Loader2 className="h-6 w-6 mr-3 animate-spin" />
                    Obtendo localizacao...
                  </>
                ) : isCreatingCheckin ? (
                  <>
                    <Loader2 className="h-6 w-6 mr-3 animate-spin" />
                    Registrando...
                  </>
                ) : checkinSuccess ? (
                  <>
                    <CheckCircle2 className="h-6 w-6 mr-3" />
                    Check-in Registrado!
                  </>
                ) : currentPosition ? (
                  <>
                    <Navigation className="h-6 w-6 mr-3" />
                    Fazer Check-in
                  </>
                ) : (
                  <>
                    <MapPin className="h-6 w-6 mr-3" />
                    Obter Localizacao
                  </>
                )}
              </Button>

              {currentPosition && (
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">
                    Lat: {currentPosition.lat.toFixed(6)} | Lng: {currentPosition.lng.toFixed(6)}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-1"
                    onClick={handleGetLocation}
                    disabled={isGettingLocation}
                  >
                    <Navigation className="h-3 w-3 mr-1" />
                    Atualizar localizacao
                  </Button>
                </div>
              )}
            </div>

            {/* Check-in Options */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo de Atividade</Label>
                <Select value={checkinTipo} onValueChange={(v) => setCheckinTipo(v as TipoCheckin)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="visita">Visita</SelectItem>
                    <SelectItem value="vistoria">Vistoria</SelectItem>
                    <SelectItem value="captacao">Captacao</SelectItem>
                    <SelectItem value="reuniao">Reuniao</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Imovel (opcional)</Label>
                <Input
                  value={checkinImovelId}
                  onChange={(e) => setCheckinImovelId(e.target.value)}
                  placeholder="ID do imovel"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Observacoes (opcional)</Label>
              <Textarea
                value={checkinNotes}
                onChange={(e) => setCheckinNotes(e.target.value)}
                placeholder="Notas sobre a visita..."
                rows={3}
              />
            </div>
          </CardContent>
        </Card>

        {/* Nearby Properties */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Home className="h-4 w-4" />
              Imoveis Proximos
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!currentPosition ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Obtenha sua localizacao para ver imoveis proximos.
              </p>
            ) : imoveisProximos && imoveisProximos.length > 0 ? (
              <div className="space-y-3">
                {imoveisProximos.slice(0, 8).map((imovel) => (
                  <div
                    key={imovel.id}
                    className="p-3 rounded-lg border hover:shadow-sm transition-shadow cursor-pointer"
                    onClick={() => setCheckinImovelId(imovel.id)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">
                          {imovel.titulo_anuncio || imovel.tipo_imovel || 'Imovel'}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {[imovel.logradouro, imovel.numero, imovel.bairro]
                            .filter(Boolean)
                            .join(', ') || 'Sem endereco'}
                        </p>
                      </div>
                      <Badge variant="outline" className="text-xs shrink-0">
                        {imovel.distancia_km.toFixed(1)} km
                      </Badge>
                    </div>
                    {imovel.valor && (
                      <p className="text-xs font-semibold text-primary mt-1">
                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(imovel.valor)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhum imovel encontrado nas proximidades.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Check-ins */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Check-ins Recentes
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoadingCheckins ? (
            <div className="py-8 text-center text-muted-foreground">Carregando...</div>
          ) : recentCheckins.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <MapPin className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhum check-in registrado</p>
              <p className="text-sm">Faca seu primeiro check-in usando o botao acima.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data/Hora</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Localizacao</TableHead>
                    <TableHead>Imovel</TableHead>
                    <TableHead>Observacoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentCheckins.map((checkin: Checkin) => (
                    <TableRow key={checkin.id}>
                      <TableCell className="whitespace-nowrap">
                        {formatDate(checkin.created_at, true)}
                      </TableCell>
                      <TableCell>
                        <Badge className={TIPO_CONFIG[checkin.tipo].className}>
                          {TIPO_CONFIG[checkin.tipo].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        <div className="flex items-center gap-1">
                          <MapPin className="h-3 w-3 text-muted-foreground" />
                          {checkin.latitude.toFixed(4)}, {checkin.longitude.toFixed(4)}
                        </div>
                      </TableCell>
                      <TableCell>
                        {checkin.imovel_id ? (
                          <span className="text-xs font-mono">{checkin.imovel_id.slice(0, 8)}...</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {checkin.observacoes || '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Inspection Dialog */}
      <Dialog open={vistoriaDialogOpen} onOpenChange={setVistoriaDialogOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardCheck className="h-5 w-5" />
              Vistoria Rapida
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {!currentPosition && (
              <div className="flex items-center gap-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                <p className="text-sm text-yellow-800 dark:text-yellow-200">
                  Obtenha sua localizacao antes de iniciar a vistoria.
                </p>
                <Button variant="outline" size="sm" onClick={handleGetLocation} disabled={isGettingLocation}>
                  {isGettingLocation ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Obter'}
                </Button>
              </div>
            )}

            <div className="space-y-2">
              <Label>ID do Imovel *</Label>
              <Input
                value={vistoriaImovelId}
                onChange={(e) => setVistoriaImovelId(e.target.value)}
                placeholder="UUID do imovel"
              />
            </div>

            <div className="space-y-2">
              <Label>Estado Geral</Label>
              <Select
                value={vistoriaEstado}
                onValueChange={(v) => setVistoriaEstado(v as typeof vistoriaEstado)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="bom">Bom</SelectItem>
                  <SelectItem value="regular">Regular</SelectItem>
                  <SelectItem value="ruim">Ruim</SelectItem>
                  <SelectItem value="critico">Critico</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Checklist */}
            <div className="space-y-3">
              <Label className="text-base font-semibold">Checklist de Vistoria</Label>
              <div className="grid grid-cols-2 gap-2">
                {CHECKLIST_ITEMS.map((item) => (
                  <label
                    key={item.key}
                    className="flex items-center gap-2 p-2 rounded-lg border cursor-pointer hover:bg-accent transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={vistoriaChecklist[item.key] || false}
                      onChange={(e) =>
                        setVistoriaChecklist({
                          ...vistoriaChecklist,
                          [item.key]: e.target.checked,
                        })
                      }
                      className="h-4 w-4"
                    />
                    <span className="text-sm">{item.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Observacoes</Label>
              <Textarea
                value={vistoriaObs}
                onChange={(e) => setVistoriaObs(e.target.value)}
                placeholder="Detalhes adicionais da vistoria..."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setVistoriaDialogOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleVistoriaSubmit}
              disabled={isCriandoVistoria || !currentPosition || !vistoriaImovelId}
            >
              {isCriandoVistoria ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Registrando...
                </>
              ) : (
                'Registrar Vistoria'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
