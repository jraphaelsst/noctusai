/** "Filtro de leads" drawer (live a8). One component file so the panel can be swapped for the seed SideDrawer. */
import { useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { filtrosVazios, useLaisCanais, type FiltrosLeads } from "@/hooks/useLaisLeads";

const OPERACOES = [["aluguel", "Aluguel"], ["compra", "Compra"], ["administracao", "Administração"]] as const;
const ATENDIMENTO = [["sem_atendimento", "Sem atendimento"], ["atendido", "Atendido pela Julia"]] as const;
const STATUS = [["enviado", "Enviado ao SW"], ["erro", "Erro no envio"], ["nao_pronto", "Não pronto"]] as const;

function Checks({
  nome, opcoes, valor, onChange,
}: { nome: string; opcoes: readonly (readonly [string, string])[]; valor: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium">{nome}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {opcoes.map(([v, l]) => (
          <label key={v} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={valor.includes(v)}
              onChange={(e) => onChange(e.target.checked ? [...valor, v] : valor.filter((x) => x !== v))} />
            {l}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function FiltroDrawer({
  filtros, onAplicar, onClose,
}: { filtros: FiltrosLeads; onAplicar: (f: FiltrosLeads) => void; onClose: () => void }) {
  const [f, setF] = useState<FiltrosLeads>(filtros);
  const canais = useLaisCanais();
  const set = <K extends keyof FiltrosLeads>(k: K, v: FiltrosLeads[K]) => setF((x) => ({ ...x, [k]: v }));
  const texto = (k: "nome" | "email" | "telefone" | "imovel" | "link" | "campanha" | "anuncio", rotulo: string) => (
    <div className="space-y-1">
      <Label htmlFor={`f-${k}`}>{rotulo}</Label>
      <Input id={`f-${k}`} value={f[k]} onChange={(e) => set(k, e.target.value)} />
    </div>
  );
  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Filtro de leads"
      testId="leads-filtro"
      footer={
        <>
          <Button variant="outline" data-testid="filtro-limpar" onClick={() => { setF(filtrosVazios()); onAplicar(filtrosVazios()); }}>Limpar</Button>
          <Button data-testid="filtro-filtrar" onClick={() => { onAplicar(f); onClose(); }}>Filtrar</Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="f-de">Primeiro contato — de</Label>
          <Input id="f-de" type="date" value={f.de} onChange={(e) => set("de", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="f-ate">até</Label>
          <Input id="f-ate" type="date" value={f.ate} onChange={(e) => set("ate", e.target.value)} />
        </div>
      </div>
      {texto("nome", "Nome")}
      {texto("email", "E-mail")}
      {texto("telefone", "Telefone")}
      {texto("imovel", "Imóvel")}
      {texto("link", "Link da conversa")}
      <Checks nome="Operação" opcoes={OPERACOES} valor={f.operacao} onChange={(v) => set("operacao", v)} />
      <Checks nome="Atendimento da Julia" opcoes={ATENDIMENTO} valor={f.atendimento} onChange={(v) => set("atendimento", v)} />
      <Checks nome="Status SW" opcoes={STATUS} valor={f.status} onChange={(v) => set("status", v)} />
      <Checks nome="Canal" opcoes={(canais.data ?? []).map((c) => [c.slug, c.label] as const)} valor={f.canal} onChange={(v) => set("canal", v)} />
      {texto("campanha", "Campanha de origem")}
      {texto("anuncio", "Anúncio de origem")}
    </SideDrawer>
  );
}
