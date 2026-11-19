/** "Horário de atendimento": the org's window (opening, closing, weekdays) that gates Julia's automatic outbound. */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  DIAS_SEMANA,
  FUSO_ATENDIMENTO,
  mensagemErroReengajamento,
  useSalvarReengajamentoConfig,
  validarHorario,
  type ReengajamentoConfig,
} from "@/hooks/useJuliaReengajamento";

/** "08:00" -> "8h", "09:30" -> "9h30" (the copy used in the other cards). */
export function rotuloHora(hhmm: string): string {
  const [h, m] = hhmm.split(":");
  return m === "00" ? `${Number(h)}h` : `${Number(h)}h${m}`;
}

/** Short summary of a window, e.g. "das 8h às 20h · todos os dias". */
export function resumoHorario(c: Pick<ReengajamentoConfig, "horario_abertura" | "horario_fechamento" | "dias_atendimento">): string {
  const dias = c.dias_atendimento;
  const rotulo =
    dias.length === 7
      ? "todos os dias"
      : dias.join(",") === "1,2,3,4,5"
        ? "de segunda a sexta"
        : DIAS_SEMANA.filter((d) => dias.includes(d.dia))
            .map((d) => d.sigla)
            .join(", ");
  return `das ${rotuloHora(c.horario_abertura)} às ${rotuloHora(c.horario_fechamento)} · ${rotulo}`;
}

export function HorarioAtendimentoCard({ config, isAdmin }: { config: ReengajamentoConfig; isAdmin: boolean }) {
  const salvar = useSalvarReengajamentoConfig();
  const [abertura, setAbertura] = useState(config.horario_abertura);
  const [fechamento, setFechamento] = useState(config.horario_fechamento);
  const [dias, setDias] = useState<number[]>(config.dias_atendimento);
  const [erro, setErro] = useState<string | null>(null);

  const alterado =
    abertura !== config.horario_abertura ||
    fechamento !== config.horario_fechamento ||
    [...dias].sort().join() !== [...config.dias_atendimento].sort().join();

  function alternarDia(dia: number) {
    setErro(null);
    setDias((atual) => (atual.includes(dia) ? atual.filter((d) => d !== dia) : [...atual, dia].sort()));
  }

  function enviar() {
    const recusa = validarHorario(abertura, fechamento, dias);
    if (recusa) {
      setErro(recusa);
      return;
    }
    setErro(null);
    salvar.mutate(
      { ...config, horario_abertura: abertura, horario_fechamento: fechamento, dias_atendimento: dias },
      {
        onSuccess: (row) => {
          setAbertura(row.horario_abertura);
          setFechamento(row.horario_fechamento);
          setDias(row.dias_atendimento);
          toast.success("Horário de atendimento salvo");
        },
        onError: (e) => setErro(mensagemErroReengajamento(e, "Não foi possível salvar o horário de atendimento.")),
      },
    );
  }

  return (
    <Card data-testid="card-horario">
      <CardHeader>
        <CardTitle className="text-base">Horário de atendimento</CardTitle>
        <CardDescription>
          A Julia só inicia mensagens automáticas dentro deste horário: o reengajamento em horas, as réguas e o primeiro contato dos
          portais. Fora dele, a mensagem espera a próxima abertura. Fuso: São Paulo ({FUSO_ATENDIMENTO}).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <Label htmlFor="horario-abertura">Abertura</Label>
            <input
              id="horario-abertura"
              type="time"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={abertura}
              disabled={!isAdmin}
              onChange={(e) => {
                setErro(null);
                setAbertura(e.target.value);
              }}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="horario-fechamento">Fechamento</Label>
            <input
              id="horario-fechamento"
              type="time"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={fechamento}
              disabled={!isAdmin}
              onChange={(e) => {
                setErro(null);
                setFechamento(e.target.value);
              }}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label id="horario-dias-rotulo">Dias da semana</Label>
          <div role="group" aria-labelledby="horario-dias-rotulo" className="flex flex-wrap gap-2">
            {DIAS_SEMANA.map((d) => {
              const ligado = dias.includes(d.dia);
              return (
                <Button
                  key={d.dia}
                  type="button"
                  size="sm"
                  variant={ligado ? "default" : "outline"}
                  aria-pressed={ligado}
                  aria-label={d.nome}
                  disabled={!isAdmin}
                  onClick={() => alternarDia(d.dia)}
                >
                  {d.sigla}
                </Button>
              );
            })}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          O fechamento é exclusivo (20:00 = já fora do horário). Horário que passa da meia-noite não é suportado.
        </p>
        {erro && (
          <p role="alert" className="text-sm text-destructive" data-testid="horario-erro">
            {erro}
          </p>
        )}
        <div className="flex justify-end">
          <Button onClick={enviar} disabled={!isAdmin || !alterado || salvar.isPending}>
            {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar horário
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
