import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Button } from "@noctusai/seed/components/ui/button";
import { Input } from "@noctusai/seed/components/ui/input";
import { Label } from "@noctusai/seed/components/ui/label";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@noctusai/seed/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RefreshCw, Settings, Users, BarChart3, Download } from "lucide-react";
import { TableSkeleton } from "@/components/ui/page-skeleton";
import {
  useMetaConfig,
  useSalvarMetaConfig,
  useMetaLeads,
  useSyncMetaLeads,
  useImportarLeadComoCliente,
  useMetaCampanhas,
  useSyncMetaCampanhas,
} from "@/hooks/useMetaApi";
import { formatCurrency } from "@/lib/utils";

export default function MetaAds() {
  const [tab, setTab] = useState("leads");

  // Config
  const { data: config } = useMetaConfig();
  const salvarConfig = useSalvarMetaConfig();
  const [configForm, setConfigForm] = useState({
    page_id: "",
    access_token: "",
    ad_account_id: "",
    webhook_verify_token: "",
  });

  // Leads
  const [leadsPage, setLeadsPage] = useState(1);
  const { data: leadsData, isLoading: leadsLoading } = useMetaLeads(leadsPage);
  const syncLeads = useSyncMetaLeads();
  const importarLead = useImportarLeadComoCliente();

  // Campaigns
  const [campanhasPage, setCampanhasPage] = useState(1);
  const { data: campanhasData, isLoading: campanhasLoading } = useMetaCampanhas(campanhasPage);
  const syncCampanhas = useSyncMetaCampanhas();

  const leads = leadsData?.data ?? [];
  const campanhas = campanhasData?.data ?? [];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Meta Ads</h1>
          <p className="text-muted-foreground">
            Gerencie leads do Facebook e acompanhe campanhas
          </p>
        </div>
        <Badge variant={config?.is_active ? "default" : "secondary"}>
          {config ? "Configurado" : "Nao configurado"}
        </Badge>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="leads">
            <Users className="h-4 w-4 mr-2" />
            Leads
          </TabsTrigger>
          <TabsTrigger value="campanhas">
            <BarChart3 className="h-4 w-4 mr-2" />
            Campanhas
          </TabsTrigger>
          <TabsTrigger value="config">
            <Settings className="h-4 w-4 mr-2" />
            Configuracao
          </TabsTrigger>
        </TabsList>

        {/* Leads Tab */}
        <TabsContent value="leads" className="space-y-4">
          <div className="flex justify-end">
            <Button
              onClick={() => syncLeads.mutate()}
              disabled={syncLeads.isPending}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${syncLeads.isPending ? "animate-spin" : ""}`} />
              Sincronizar Leads
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Lead ID</TableHead>
                    <TableHead>Formulario</TableHead>
                    <TableHead>Dados</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {leadsLoading ? (
                    <TableRow>
                      <TableCell colSpan={5} className="p-0">
                        <TableSkeleton rows={3} />
                      </TableCell>
                    </TableRow>
                  ) : leads.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                        Nenhum lead encontrado. Clique em "Sincronizar Leads" para buscar.
                      </TableCell>
                    </TableRow>
                  ) : (
                    leads.map((lead) => (
                      <TableRow key={lead.id}>
                        <TableCell className="font-mono text-xs">
                          {lead.lead_id.slice(0, 12)}...
                        </TableCell>
                        <TableCell>{lead.form_name || lead.form_id || "-"}</TableCell>
                        <TableCell className="max-w-[200px]">
                          <div className="text-xs space-y-0.5">
                            {Object.entries(lead.campo_data).slice(0, 3).map(([k, v]) => (
                              <div key={k}>
                                <span className="font-medium">{k}:</span> {v}
                              </div>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={lead.importado ? "default" : "outline"}>
                            {lead.importado ? "Importado" : "Pendente"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {!lead.importado && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => importarLead.mutate(lead.id)}
                              disabled={importarLead.isPending}
                            >
                              <Download className="h-3 w-3 mr-1" />
                              Importar
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Campaigns Tab */}
        <TabsContent value="campanhas" className="space-y-4">
          <div className="flex justify-end">
            <Button
              onClick={() => syncCampanhas.mutate()}
              disabled={syncCampanhas.isPending}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${syncCampanhas.isPending ? "animate-spin" : ""}`} />
              Sincronizar Campanhas
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Campanha</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Gasto</TableHead>
                    <TableHead className="text-right">Impressoes</TableHead>
                    <TableHead className="text-right">Cliques</TableHead>
                    <TableHead className="text-right">Leads</TableHead>
                    <TableHead className="text-right">CPL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {campanhasLoading ? (
                    <TableRow>
                      <TableCell colSpan={7} className="p-0">
                        <TableSkeleton rows={3} />
                      </TableCell>
                    </TableRow>
                  ) : campanhas.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        Nenhuma campanha sincronizada.
                      </TableCell>
                    </TableRow>
                  ) : (
                    campanhas.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="font-medium">{c.nome || c.campaign_id}</TableCell>
                        <TableCell>
                          <Badge variant={c.status === "ACTIVE" ? "default" : "secondary"}>
                            {c.status || "-"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">{formatCurrency(c.spend)}</TableCell>
                        <TableCell className="text-right">{c.impressions.toLocaleString("pt-BR")}</TableCell>
                        <TableCell className="text-right">{c.clicks.toLocaleString("pt-BR")}</TableCell>
                        <TableCell className="text-right">{c.leads}</TableCell>
                        <TableCell className="text-right">
                          {c.cpl ? formatCurrency(c.cpl) : "-"}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Config Tab */}
        <TabsContent value="config">
          <Card>
            <CardHeader>
              <CardTitle>Configuracao da API Meta</CardTitle>
              <CardDescription>
                Configure as credenciais do Facebook/Instagram para sincronizar leads e campanhas.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="page_id">Page ID</Label>
                  <Input
                    id="page_id"
                    placeholder="ID da pagina do Facebook"
                    value={configForm.page_id}
                    onChange={(e) => setConfigForm((p) => ({ ...p, page_id: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ad_account_id">Ad Account ID</Label>
                  <Input
                    id="ad_account_id"
                    placeholder="ID da conta de anuncios"
                    value={configForm.ad_account_id}
                    onChange={(e) => setConfigForm((p) => ({ ...p, ad_account_id: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="access_token">Access Token</Label>
                  <Input
                    id="access_token"
                    type="password"
                    placeholder="Token de acesso da API"
                    value={configForm.access_token}
                    onChange={(e) => setConfigForm((p) => ({ ...p, access_token: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="webhook_verify_token">Webhook Verify Token</Label>
                  <Input
                    id="webhook_verify_token"
                    placeholder="Token de verificacao do webhook"
                    value={configForm.webhook_verify_token}
                    onChange={(e) =>
                      setConfigForm((p) => ({ ...p, webhook_verify_token: e.target.value }))
                    }
                  />
                </div>
              </div>
              <Button
                onClick={() => salvarConfig.mutate(configForm)}
                disabled={salvarConfig.isPending}
              >
                Salvar Configuracao
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
