import { useState } from 'react';
import { ShieldCheck, AlertTriangle, Ban, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useAdminReports, useResolveReport, useAdminBlocks } from '@/hooks/useAdmin';

const REPORT_STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pending: { label: 'Pendente', variant: 'outline' },
  resolved: { label: 'Resolvido', variant: 'default' },
  dismissed: { label: 'Descartado', variant: 'secondary' },
};

interface Report {
  id: string;
  reporter_name: string;
  reported_message_preview: string;
  reason: string;
  status: string;
  created_at: string;
  conversation_id?: string;
}

interface Block {
  id: string;
  blocker_name: string;
  blocked_name: string;
  created_at: string;
}

export default function AdminModeration() {
  const { data: reportsData, isLoading: reportsLoading } = useAdminReports();
  const { data: blocksData, isLoading: blocksLoading } = useAdminBlocks();
  const resolveReport = useResolveReport();

  const [resolveDialogOpen, setResolveDialogOpen] = useState(false);
  const [resolveTarget, setResolveTarget] = useState<string | null>(null);
  const [resolution, setResolution] = useState('');

  const reports = (reportsData?.data ?? []) as Report[];
  const blocks = (blocksData?.data ?? []) as Block[];

  const handleResolve = () => {
    if (!resolveTarget || !resolution.trim()) return;
    resolveReport.mutate({ id: resolveTarget, resolution: resolution.trim() });
    setResolveDialogOpen(false);
    setResolveTarget(null);
    setResolution('');
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ShieldCheck className="h-6 w-6" /> Moderacao
        </h1>
        <p className="text-muted-foreground">Gerenciar denuncias e bloqueios de usuarios</p>
      </div>

      <Tabs defaultValue="denuncias">
        <TabsList>
          <TabsTrigger value="denuncias" className="gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5" /> Denuncias
            {reports.filter(r => r.status === 'pending').length > 0 && (
              <Badge variant="destructive" className="ml-1 h-5 min-w-[20px] px-1.5 text-[10px]">
                {reports.filter(r => r.status === 'pending').length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="bloqueios" className="gap-1.5">
            <Ban className="h-3.5 w-3.5" /> Bloqueios
          </TabsTrigger>
        </TabsList>

        <TabsContent value="denuncias" className="mt-4">
          {reportsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Card key={i} className="animate-pulse">
                  <CardContent className="p-4 h-24" />
                </Card>
              ))}
            </div>
          ) : reports.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <CheckCircle className="h-12 w-12 text-green-500/30 mx-auto mb-4" />
                <p className="text-lg font-medium text-muted-foreground">
                  Nenhuma denuncia registrada
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {reports.map(r => {
                const badge = REPORT_STATUS_BADGE[r.status] ?? REPORT_STATUS_BADGE.pending;
                return (
                  <Card key={r.id}>
                    <CardContent className="p-4">
                      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                        <div className="flex-1 space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm">Denunciante: {r.reporter_name}</span>
                            <Badge variant={badge.variant}>{badge.label}</Badge>
                          </div>
                          <div className="bg-muted/50 p-3 rounded-md">
                            <p className="text-sm italic text-muted-foreground">
                              "{r.reported_message_preview}"
                            </p>
                          </div>
                          <p className="text-sm">
                            <span className="font-medium">Motivo:</span> {r.reason}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {new Date(r.created_at).toLocaleString('pt-BR')}
                          </p>
                        </div>
                        {r.status === 'pending' && (
                          <div className="flex gap-2 shrink-0">
                            <Button
                              size="sm"
                              onClick={() => {
                                setResolveTarget(r.id);
                                setResolution('');
                                setResolveDialogOpen(true);
                              }}
                            >
                              Resolver
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                            >
                              Ver Conversa
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="bloqueios" className="mt-4">
          {blocksLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Card key={i} className="animate-pulse">
                  <CardContent className="p-4 h-16" />
                </Card>
              ))}
            </div>
          ) : blocks.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Ban className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
                <p className="text-lg font-medium text-muted-foreground">
                  Nenhum bloqueio registrado
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              <div className="hidden md:grid grid-cols-3 gap-4 px-4 py-2 text-sm font-medium text-muted-foreground">
                <span>Bloqueador</span>
                <span>Bloqueado</span>
                <span>Data</span>
              </div>
              {blocks.map(b => (
                <Card key={b.id}>
                  <CardContent className="p-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                      <p className="text-sm font-medium">{b.blocker_name}</p>
                      <p className="text-sm">{b.blocked_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {new Date(b.created_at).toLocaleString('pt-BR')}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Resolve dialog */}
      <Dialog open={resolveDialogOpen} onOpenChange={setResolveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolver denuncia</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">
              Descricao da resolucao
            </label>
            <Input
              value={resolution}
              onChange={e => setResolution(e.target.value)}
              placeholder="Descreva a acao tomada..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolveDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleResolve} disabled={!resolution.trim()}>
              Confirmar resolucao
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
