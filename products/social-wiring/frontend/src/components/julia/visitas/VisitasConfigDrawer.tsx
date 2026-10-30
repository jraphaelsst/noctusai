/**
 * Visit-request config drawer (live Julia a3). One config, or — with
 * "Diferenciar configuração…" — one per operation (compra / aluguel).
 * Admin-only writes (server-enforced; the UI just disables the form).
 */
import { useState } from "react";
import { toast } from "sonner";

import { SideDrawer } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  DIAS, DIA_LABEL, mensagemErroVisitas, operacaoPadrao, useSalvarVisitasConfig,
  type Dia, type Operacao, type OperacaoConfig, type VisitasConfig,
} from "@/hooks/useJuliaVisitas";

const OPS: { key: Operacao; label: string }[] = [
  { key: "compra", label: "Compra" },
  { key: "aluguel", label: "Aluguel" },
];

function clonar(c: VisitasConfig | undefined): VisitasConfig {
  const base = c ?? { separar_operacao: false, config: {} };
  const config: VisitasConfig["config"] = {};
  for (const k of ["geral", "compra", "aluguel"] as Operacao[]) {
    const o = base.config?.[k];
    config[k] = { ...operacaoPadrao(), ...(o ?? {}), grade: { ...operacaoPadrao().grade, ...(o?.grade ?? {}) } };
  }
  return { separar_operacao: !!base.separar_operacao, config };
}

interface Props { config: VisitasConfig | undefined; isAdmin: boolean; onClose: () => void }

export function VisitasConfigDrawer({ config, isAdmin, onClose }: Props) {
  const [draft, setDraft] = useState(() => clonar(config));
  const [aba, setAba] = useState<"compra" | "aluguel">("compra");
  const salvar = useSalvarVisitasConfig();
  const chave: Operacao = draft.separar_operacao ? aba : "geral";
  const op = draft.config[chave] as OperacaoConfig;
  const ro = !isAdmin || salvar.isPending;

  const patch = (p: Partial<OperacaoConfig>) =>
    setDraft((d) => ({ ...d, config: { ...d.config, [chave]: { ...(d.config[chave] as OperacaoConfig), ...p } } }));
  const num = (v: string) => Math.max(0, Number.parseInt(v, 10) || 0);
  const faixa = (d: Dia) => op.grade[d]?.[0] ?? { inicio: "", fim: "" };
  const setFaixa = (d: Dia, k: "inicio" | "fim", v: string) => {
    const f = { ...faixa(d), [k]: v };
    patch({ grade: { ...op.grade, [d]: f.inicio || f.fim ? [f] : [] } });
  };
  const incompleta = DIAS.some((d) => { const f = faixa(d); return !!f.inicio !== !!f.fim || (f.inicio && f.fim && f.fim <= f.inicio); });

  const onSalvar = () =>
    salvar.mutate(draft, {
      onSuccess: () => { toast.success("Configuração de visitas salva"); onClose(); },
      onError: (e) => toast.error(mensagemErroVisitas(e, "Não foi possível salvar a configuração.")),
    });

  const chip = (
    <span data-testid="visitas-status-chip"
      className={`rounded-full px-2 py-0.5 text-xs ${op.ativo ? "bg-success-light text-success" : "bg-muted text-muted-foreground"}`}>
      {op.ativo ? "Ativo" : "Inativo"}
    </span>
  );

  return (
    <SideDrawer open onOpenChange={(o) => !o && onClose()} title="Configurar visitas" statusChip={chip}
      testId="visitas-drawer" width="md"
      footer={
        <Button className="w-full" disabled={ro || incompleta} onClick={onSalvar}>
          {salvar.isPending ? "Salvando…" : "Salvar"}
        </Button>
      }>
      {!isAdmin && <p className="mb-3 text-xs text-muted-foreground" data-testid="visitas-readonly">Somente owner/admin pode alterar.</p>}

      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="v-separar">Diferenciar configuração para leads de compra e aluguel</Label>
          <Switch id="v-separar" checked={draft.separar_operacao} disabled={ro}
            onCheckedChange={(v) => setDraft((d) => ({ ...d, separar_operacao: v }))} />
        </div>

        {draft.separar_operacao && (
          <div role="tablist" className="flex gap-2">
            {OPS.map((o) => (
              <Button key={o.key} role="tab" aria-selected={aba === o.key} size="sm"
                variant={aba === o.key ? "default" : "outline"} onClick={() => setAba(o.key as "compra" | "aluguel")}>
                {o.label}
              </Button>
            ))}
          </div>
        )}

        <div className="flex items-start justify-between gap-3">
          <div>
            <Label htmlFor="v-ativo">Pré-agendamento de visita</Label>
            <p className="text-xs text-muted-foreground">A Julia recebe pedidos de visita no pré-atendimento e eles chegam na página Visitas.</p>
          </div>
          <Switch id="v-ativo" checked={op.ativo} disabled={ro} onCheckedChange={(v) => patch({ ativo: v })} />
        </div>

        <div className="flex items-start justify-between gap-3">
          <div>
            <Label htmlFor="v-cpf">Solicitação de CPF obrigatória?</Label>
            <p className="text-xs text-muted-foreground">O CPF só é guardado de forma protegida (hash e 3 últimos dígitos).</p>
          </div>
          <Switch id="v-cpf" checked={op.cpf_obrigatorio} disabled={ro} onCheckedChange={(v) => patch({ cpf_obrigatorio: v })} />
        </div>

        <section className="space-y-3">
          <h3 className="text-sm font-medium">Período disponível para solicitação de visitas</h3>
          <div className="grid grid-cols-3 gap-2">
            <div><Label htmlFor="v-mind">Tempo mínimo (dias)</Label>
              <Input id="v-mind" type="number" min={0} value={op.min_dias} disabled={ro} onChange={(e) => patch({ min_dias: num(e.target.value) })} /></div>
            <div><Label htmlFor="v-minh">Tempo mínimo (horas)</Label>
              <Input id="v-minh" type="number" min={0} max={23} value={op.min_horas} disabled={ro} onChange={(e) => patch({ min_horas: num(e.target.value) })} /></div>
            <div><Label htmlFor="v-maxd">Tempo máximo (dias)</Label>
              <Input id="v-maxd" type="number" min={0} value={op.max_dias} disabled={ro} onChange={(e) => patch({ max_dias: num(e.target.value) })} /></div>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-medium">Horários disponíveis</h3>
          <p className="text-xs text-muted-foreground">Intervalos de 30 minutos. Deixe vazio para dia sem visitas.</p>
          {DIAS.map((d) => (
            <div key={d} className="grid grid-cols-[5.5rem_1fr_1fr] items-center gap-2" data-testid={`grade-${d}`}>
              <span className="text-sm">{DIA_LABEL[d]}</span>
              <Input type="time" step={1800} aria-label={`${DIA_LABEL[d]} de`} value={faixa(d).inicio} disabled={ro} onChange={(e) => setFaixa(d, "inicio", e.target.value)} />
              <Input type="time" step={1800} aria-label={`${DIA_LABEL[d]} até`} value={faixa(d).fim} disabled={ro} onChange={(e) => setFaixa(d, "fim", e.target.value)} />
            </div>
          ))}
          {incompleta && <p role="alert" className="text-xs text-destructive">Informe De e Até em cada dia, com o fim depois do início.</p>}
        </section>
      </div>

    </SideDrawer>
  );
}
