import { useState, useEffect } from "react";
import { Settings, Loader2 } from "lucide-react";
import { Button } from "@noctusai/seed/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@noctusai/seed/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@noctusai/seed/components/ui/card";
import { Label } from "@noctusai/seed/components/ui/label";
import { Input } from "@noctusai/seed/components/ui/input";
import { Switch } from "@noctusai/seed/components/ui/switch";
import { Separator } from "@noctusai/seed/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@noctusai/seed/components/ui/tooltip";
import { useMetasConfig, useUpsertMetaConfig, MetaConfigForm } from "@/hooks/useMetasConfig";
import { TipoMeta, CategoriaMeta } from "@/types";
import { categoriaLabels, categoriasDisponiveis } from "@/lib/categorias";
import { toast } from "sonner";

const tipoLabels: Record<TipoMeta, string> = {
  diaria: "Diárias",
  semanal: "Semanais",
  mensal: "Mensais",
  anual: "Anuais",
};

export function ConfiguracoesMetasModal() {
  const [open, setOpen] = useState(false);
  const { data: configs, isLoading: isLoadingConfigs } = useMetasConfig();
  const upsertConfig = useUpsertMetaConfig();
  const [formData, setFormData] = useState<Record<string, number | string>>({});
  const [activeStates, setActiveStates] = useState<Record<string, boolean>>({});

  // Sincronizar dados quando configs carregarem
  useEffect(() => {
    if (configs) {
      const newFormData: Record<string, number | string> = {};
      const newActiveStates: Record<string, boolean> = {};

      configs.forEach((config) => {
        const key = `${config.tipo}-${config.categoria}`;
        newFormData[key] = config.meta_pretendida;
        newActiveStates[key] = config.ativo;
      });

      setFormData(newFormData);
      setActiveStates(newActiveStates);
    }
  }, [configs]);

  const getConfigValue = (tipo: TipoMeta, categoria: CategoriaMeta) => {
    const key = `${tipo}-${categoria}`;
    const value = formData[key];
    return value === undefined || value === 0 ? "" : value;
  };

  const getActiveState = (tipo: TipoMeta, categoria: CategoriaMeta) => {
    const key = `${tipo}-${categoria}`;
    return activeStates[key] ?? true;
  };

  const handleValueChange = (tipo: TipoMeta, categoria: CategoriaMeta, value: string) => {
    const key = `${tipo}-${categoria}`;
    setFormData((prev) => ({ ...prev, [key]: parseInt(value) || 0 }));
  };

  const handleActiveChange = (tipo: TipoMeta, categoria: CategoriaMeta, checked: boolean) => {
    const key = `${tipo}-${categoria}`;
    setActiveStates((prev) => ({ ...prev, [key]: checked }));
  };

  const handleSaveAll = async () => {
    try {
      const configsToSave: MetaConfigForm[] = [];

      categoriasDisponiveis.forEach((categoria) => {
        const tipo = "mensal" as TipoMeta;
        const key = `${tipo}-${categoria}`;
        const rawValue = formData[key];
        const valueNormalized = Number(rawValue ?? 0); // '' | undefined -> 0
        const activeNormalized = activeStates[key] ?? true; // default ativo

        configsToSave.push({
          categoria,
          meta_pretendida: isNaN(valueNormalized) ? 0 : valueNormalized,
          ativo: activeNormalized,
        });
      });

      await Promise.all(configsToSave.map((config) => upsertConfig.mutateAsync(config)));

      setOpen(false);
    } catch (error) {
      toast.error("Erro", { description: "Erro ao salvar configurações." });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Settings className="mr-2 h-4 w-4" />
          Configurações
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Configurações de Metas</DialogTitle>
        </DialogHeader>

        {isLoadingConfigs ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-6 py-4">
            <p className="text-muted-foreground text-sm">
              Configure suas metas mensais. Metas diárias, semanais e anuais são geradas automaticamente com base
              nos valores mensais.
            </p>

            {(["mensal"] as TipoMeta[]).map((tipo) => (
              <Card key={tipo}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <CardTitle>Metas {tipoLabels[tipo]}</CardTitle>
                      <CardDescription>
                        Defina suas metas mensais. As metas diárias, semanais e anuais serão calculadas automaticamente.
                      </CardDescription>
                    </div>
                    <Button onClick={handleSaveAll} disabled={upsertConfig.isPending} size="lg" className="shrink-0">
                      {upsertConfig.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Salvar
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <TooltipProvider>
                    {categoriasDisponiveis.map((categoria, index) => (
                      <div key={categoria}>
                        {index > 0 && <Separator className="my-4" />}
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex-1">
                            <Label htmlFor={`${tipo}-${categoria}`}>{categoriaLabels[categoria]}</Label>
                            <Input
                              id={`${tipo}-${categoria}`}
                              type="number"
                              min="0"
                              value={getConfigValue(tipo, categoria)}
                              onChange={(e) => handleValueChange(tipo, categoria, e.target.value)}
                              className="mt-2"
                              disabled={!getActiveState(tipo, categoria)}
                              placeholder="0"
                            />
                          </div>
                          <div className="flex items-center justify-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div>
                                  <Switch
                                    id={`${tipo}-${categoria}-active`}
                                    checked={getActiveState(tipo, categoria)}
                                    onCheckedChange={(checked) => handleActiveChange(tipo, categoria, checked)}
                                  />
                                </div>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>
                                  {getActiveState(tipo, categoria)
                                    ? "Desativar criação automática das metas."
                                    : "Ativar criação automática das metas."}
                                </p>
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        </div>
                      </div>
                    ))}
                  </TooltipProvider>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
