/** Envio policy cards: Leads frios · Potenciais captações · WhatsApp inválido · Pesquisa com clientes. */
import { useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  FRIOS_MINUTOS,
  mensagemErroEnvio,
  rotuloMinutos,
  useSalvarEnvioPoliticas,
  type Politicas,
} from "@/hooks/useJuliaEnvio";

function Radio({
  name, value, atual, label, ro, onPick,
}: { name: string; value: string; atual: string; label: string; ro: boolean; onPick: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="radio" name={name} value={value} checked={atual === value} disabled={ro} onChange={() => onPick(value)} />
      {label}
    </label>
  );
}

export function PoliticasCards({ politicas, isAdmin }: { politicas: Politicas; isAdmin: boolean }) {
  const salvar = useSalvarEnvioPoliticas();
  const [erro, setErro] = useState<string | null>(null);
  const ro = !isAdmin || salvar.isPending;

  /** Every control saves the whole policy object at once (small, idempotent PUT). */
  const gravar = (patch: Partial<Politicas>) => {
    setErro(null);
    salvar.mutate({ ...politicas, ...patch }, {
      onSuccess: () => toast.success("Política de envio salva"),
      onError: (e) => setErro(mensagemErroEnvio(e, "Não foi possível salvar a política.")),
    });
  };
  const frios = politicas.frios;

  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="politicas">
      <Card data-testid="card-frios">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base"><Label htmlFor="sw-frios">Leads frios</Label></CardTitle>
            <Switch id="sw-frios" checked={frios.ativo} disabled={ro} onCheckedChange={(v) => gravar({ frios: { ...frios, ativo: v } })} />
          </div>
          <CardDescription>Envia ao SW o lead que parou de responder depois da última tentativa de reengajamento.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Radio name="frios-modo" value="intervalo" atual={frios.modo} label="Após um intervalo" ro={ro || !frios.ativo}
            onPick={() => gravar({ frios: { ...frios, modo: "intervalo" } })} />
          <select aria-label="Intervalo" className="h-9 w-full rounded-md border bg-background px-2 text-sm"
            disabled={ro || !frios.ativo || frios.modo !== "intervalo"} value={frios.minutos}
            onChange={(e) => gravar({ frios: { ...frios, minutos: Number(e.target.value) } })}>
            {FRIOS_MINUTOS.map((m) => <option key={m} value={m}>{rotuloMinutos(m)}</option>)}
          </select>
          <Radio name="frios-modo" value="manha_seguinte" atual={frios.modo} label="Na manhã seguinte (entre 5h e 6h)" ro={ro || !frios.ativo}
            onPick={() => gravar({ frios: { ...frios, modo: "manha_seguinte" } })} />
        </CardContent>
      </Card>

      <Card data-testid="card-captacoes">
        <CardHeader>
          <CardTitle className="text-base">Potenciais captações</CardTitle>
          <CardDescription>O que fazer quando a Julia identificar um imóvel potencialmente captado.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Radio name="captacoes" value="enviar" atual={politicas.captacoes} label="Enviar ao SW" ro={ro} onPick={() => gravar({ captacoes: "enviar" })} />
          <Radio name="captacoes" value="notificar" atual={politicas.captacoes} label="Só notificar" ro={ro} onPick={() => gravar({ captacoes: "notificar" })} />
        </CardContent>
      </Card>

      <Card data-testid="card-invalido">
        <CardHeader>
          <CardTitle className="text-base">WhatsApp inválido</CardTitle>
          <CardDescription>Leads cujo número não tem WhatsApp.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Radio name="invalido" value="enviar" atual={politicas.whatsapp_invalido ? "enviar" : "nao"} label="Enviar ao SW" ro={ro} onPick={() => gravar({ whatsapp_invalido: true })} />
          <Radio name="invalido" value="nao" atual={politicas.whatsapp_invalido ? "enviar" : "nao"} label="Não enviar" ro={ro} onPick={() => gravar({ whatsapp_invalido: false })} />
        </CardContent>
      </Card>

      <Card data-testid="card-pesquisa">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base"><Label htmlFor="sw-pesquisa">Pesquisa com clientes</Label></CardTitle>
            <Switch id="sw-pesquisa" checked={politicas.pesquisa} disabled={ro} onCheckedChange={(v) => gravar({ pesquisa: v })} />
          </div>
          <CardDescription>Pesquisa semanal com uma amostra aleatória de clientes. O envio requer a API oficial do WhatsApp.</CardDescription>
        </CardHeader>
      </Card>
      {erro && <p role="alert" className="text-sm text-destructive md:col-span-2" data-testid="politicas-erro">{erro}</p>}
    </div>
  );
}
