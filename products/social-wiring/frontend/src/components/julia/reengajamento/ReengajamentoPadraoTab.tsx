/** Tab "Reengajamento padrão": minutes + hours cards, each with an [Editar] drawer. */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SideDrawer } from "@noctusai/lib/components";
import {
  HORAS_OPCOES,
  MINUTOS_OPCOES,
  mensagemErroReengajamento,
  useReengajamentoConfig,
  useSalvarReengajamentoConfig,
  type ReengajamentoConfig,
} from "@/hooks/useJuliaReengajamento";

type Modo = "minutos" | "horas";

export function rotuloMinutos(v: number): string {
  return v === 60 ? "1 hora" : `${v} minutos`;
}
export function rotuloHoras(v: number): string {
  return v === 1 ? "1 hora" : `${v} horas`;
}

function ConfigDrawer({
  modo,
  config,
  isAdmin,
  onClose,
}: {
  modo: Modo;
  config: ReengajamentoConfig;
  isAdmin: boolean;
  onClose: () => void;
}) {
  const salvar = useSalvarReengajamentoConfig();
  const min = modo === "minutos";
  const [ativo, setAtivo] = useState(min ? config.minutos_ativo : config.horas_ativo);
  const [intervalo, setIntervalo] = useState(min ? config.minutos_intervalo : config.horas_intervalo);
  const [erro, setErro] = useState<string | null>(null);
  const opcoes: readonly number[] = min ? MINUTOS_OPCOES : HORAS_OPCOES;

  function enviar() {
    setErro(null);
    const body: ReengajamentoConfig = min
      ? { ...config, minutos_ativo: ativo, minutos_intervalo: intervalo }
      : { ...config, horas_ativo: ativo, horas_intervalo: intervalo };
    salvar.mutate(body, {
      onSuccess: () => {
        toast.success("Reengajamento salvo");
        onClose();
      },
      onError: (e) => setErro(mensagemErroReengajamento(e, "Não foi possível salvar o reengajamento.")),
    });
  }

  return (
    <div className="space-y-4" data-testid={`drawer-${modo}-body`}>
      <div className="flex items-center justify-between">
        <Label htmlFor={`sw-${modo}`}>{min ? "Reengajamento em minutos" : "Reengajamento em horas"}</Label>
        <Switch id={`sw-${modo}`} checked={ativo} onCheckedChange={setAtivo} disabled={!isAdmin} />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`int-${modo}`}>Intervalo</Label>
        <select
          id={`int-${modo}`}
          className="h-9 w-full rounded-md border bg-background px-2 text-sm"
          value={intervalo}
          disabled={!isAdmin}
          onChange={(e) => setIntervalo(Number(e.target.value))}
        >
          {opcoes.map((v) => (
            <option key={v} value={v}>
              {min ? rotuloMinutos(v) : rotuloHoras(v)}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          {min ? "Funciona em qualquer horário" : "Funciona das 8h às 20h"}
        </p>
      </div>
      <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground space-y-1">
        {min ? (
          <>
            <p>Se o lead responder, o fluxo de reengajamento recomeça.</p>
            <p>Leads que encerraram a conversa nunca são contatados.</p>
            <p>Leads que nunca responderam são cobertos pelo reengajamento em horas.</p>
          </>
        ) : (
          <>
            <p>Atende leads que pararam de responder ou que nunca responderam.</p>
            <p>Se o lead responder, o fluxo de reengajamento recomeça.</p>
            <p>Leads que encerraram a conversa nunca são contatados.</p>
          </>
        )}
      </div>
      {erro && (
        <p role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button onClick={enviar} disabled={!isAdmin || salvar.isPending}>
          {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Salvar
        </Button>
      </div>
    </div>
  );
}

export function ReengajamentoPadraoTab({ isAdmin }: { isAdmin: boolean }) {
  const q = useReengajamentoConfig();
  const [aberto, setAberto] = useState<Modo | null>(null);
  const showSkeleton = q.isPending && !q.data;

  if (showSkeleton) {
    return (
      <div className="space-y-4" data-testid="reeng-skeleton">
        {[0, 1].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    );
  }
  if (!q.data) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground" data-testid="reeng-erro">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm">Não foi possível carregar o reengajamento.</p>
        <Button variant="outline" size="sm" onClick={() => q.refetch()}>
          Tentar de novo
        </Button>
      </div>
    );
  }
  const c = q.data;
  const cards: { modo: Modo; titulo: string; ativo: boolean; resumo: string; copy: string }[] = [
    {
      modo: "minutos",
      titulo: "Reengajamento em minutos",
      ativo: c.minutos_ativo,
      resumo: `A cada ${rotuloMinutos(c.minutos_intervalo)} sem resposta`,
      copy: "Funciona em qualquer horário",
    },
    {
      modo: "horas",
      titulo: "Reengajamento em horas",
      ativo: c.horas_ativo,
      resumo: `A cada ${rotuloHoras(c.horas_intervalo)} sem resposta`,
      copy: "Funciona das 8h às 20h",
    },
  ];
  return (
    <div className="space-y-4">
      {cards.map((k) => (
        <Card key={k.modo} data-testid={`card-${k.modo}`}>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">{k.titulo}</CardTitle>
              <CardDescription>
                {k.resumo} · {k.copy}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={k.ativo ? "default" : "secondary"}>{k.ativo ? "Ativo" : "Inativo"}</Badge>
              <Button variant="outline" size="sm" onClick={() => setAberto(k.modo)}>
                Editar
              </Button>
            </div>
          </CardHeader>
          <CardContent className="sr-only" />
        </Card>
      ))}
      {aberto && (
        <SideDrawer
          open
          onOpenChange={(o) => !o && setAberto(null)}
          title={aberto === "minutos" ? "Editar reengajamento em minutos" : "Editar reengajamento em horas"}
          testId={`drawer-${aberto}`}
        >
          <ConfigDrawer modo={aberto} config={c} isAdmin={isAdmin} onClose={() => setAberto(null)} />
        </SideDrawer>
      )}
    </div>
  );
}
