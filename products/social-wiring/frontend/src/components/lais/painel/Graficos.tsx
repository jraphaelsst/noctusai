import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Painel } from "@/hooks/useLaisPainel";

const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

function Card({ titulo, nota, children, testid }: { titulo: string; nota?: string; children: ReactNode; testid: string }) {
  return (
    <div className="rounded-lg border bg-card p-4" data-testid={testid}>
      <h3 className="text-sm font-semibold">{titulo}</h3>
      {nota && <p className="text-xs text-muted-foreground">{nota}</p>}
      <div className="mt-2 h-56">{children}</div>
    </div>
  );
}

function Barras({ data, x, series }: { data: object[]; x: string; series: { key: string; nome: string; cor: string }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={x} fontSize={11} />
        <YAxis allowDecimals={false} fontSize={11} />
        <Tooltip />
        {series.length > 1 && <Legend />}
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.nome} fill={s.cor} stackId={series.length > 1 ? "a" : undefined} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function Lista({ id, itens }: { id: string; itens: string[] }) {
  return <ul className="sr-only" data-testid={id}>{itens.map((t) => <li key={t}>{t}</li>)}</ul>;
}

export function Graficos({ p }: { p: Painel }) {
  const horas = p.por_hora.map((total, h) => ({ hora: `${h}h`, total }));
  const semana = p.por_dia_semana.map((total, i) => ({ dia: DIAS[i].slice(0, 3), total }));
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card titulo="Leads por canal" testid="grafico-por-canal">
        <Barras data={p.por_canal} x="canal" series={[{ key: "total", nome: "Leads", cor: "#6366f1" }]} />
        <Lista id="dados-por-canal" itens={p.por_canal.map((c) => `${c.canal}: ${c.total}`)} />
      </Card>
      <Card titulo="Status por canal" testid="grafico-status-canal">
        <Barras data={p.status_por_canal} x="canal" series={[
          { key: "enviado", nome: "Enviado ao SW", cor: "#22c55e" },
          { key: "nao_pronto", nome: "Não pronto", cor: "#f59e0b" },
          { key: "erro", nome: "Erro no envio", cor: "#ef4444" },
        ]} />
        <Lista id="dados-status-canal" itens={p.status_por_canal.map((c) => `${c.canal}: enviado ${c.enviado}, não pronto ${c.nao_pronto}, erro ${c.erro}`)} />
      </Card>
      <Card titulo="Leads por horário no mês" nota={`${p.fora_horario_pct}% fora do horário comercial`} testid="grafico-por-hora">
        <Barras data={horas} x="hora" series={[{ key: "total", nome: "Leads", cor: "#6366f1" }]} />
        <Lista id="dados-por-hora" itens={horas.map((h) => `${h.hora}: ${h.total}`)} />
      </Card>
      <Card titulo="Leads semanais" nota={p.melhor_dia != null && DIAS[p.melhor_dia] ? `Melhor dia da semana: ${DIAS[p.melhor_dia]}` : undefined} testid="grafico-semana">
        <Barras data={semana} x="dia" series={[{ key: "total", nome: "Leads", cor: "#6366f1" }]} />
        <Lista id="dados-semana" itens={semana.map((d) => `${d.dia}: ${d.total}`)} />
      </Card>
      <div className="lg:col-span-2">
        <Card titulo="Leads nos últimos 6 meses" testid="grafico-seis-meses">
          <Barras data={p.seis_meses} x="mes" series={[
            { key: "enviado", nome: "Enviado", cor: "#22c55e" },
            { key: "nao_enviado", nome: "Não enviado", cor: "#94a3b8" },
          ]} />
          <Lista id="dados-seis-meses" itens={p.seis_meses.map((m) => `${m.mes}: enviado ${m.enviado}, não enviado ${m.nao_enviado}`)} />
        </Card>
      </div>
    </div>
  );
}
