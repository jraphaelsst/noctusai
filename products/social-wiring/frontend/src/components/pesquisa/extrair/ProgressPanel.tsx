import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { isJobActive, type ExtractionJob } from "@/hooks/usePesquisaExtracao";

interface ProgressPanelProps {
  job: ExtractionJob;
  onCancelar: () => void;
  cancelando: boolean;
  onTentarNovamente: () => void;
}

function Contadores({ job }: { job: ExtractionJob }) {
  return (
    <p className="text-sm text-muted-foreground">
      {job.tarefas_processadas}/{job.total_tarefas} post(s) · {job.itens_salvos} item(ns) novo(s) ·{" "}
      {job.itens_ignorados} já existente(s) · {job.assuntos_salvos} assunto(s)
      {job.tarefas_com_erro > 0 ? ` · ${job.tarefas_com_erro} com erro` : ""}
    </p>
  );
}

function Resultado({ job }: { job: ExtractionJob }) {
  return (
    <div className="flex flex-col gap-1">
      <Contadores job={job} />
      {job.itens_descartados > 0 && (
        <p className="text-sm text-muted-foreground">{job.itens_descartados} item(ns) descartado(s)</p>
      )}
      {job.ja_extraidos_pulados > 0 && (
        <p className="text-sm text-muted-foreground">{job.ja_extraidos_pulados} post(s) já extraído(s) pulado(s)</p>
      )}
      <div className="flex gap-4 text-sm">
        <Link className="text-primary hover:underline" to="/media-creation/pesquisa?status=pending">
          Ver pendentes em Minha Pesquisa
        </Link>
        <Link className="text-primary hover:underline" to="/media-creation/pesquisa?tab=assuntos-virais">
          Ver assuntos virais
        </Link>
      </div>
    </div>
  );
}

export function ProgressPanel({ job, onCancelar, cancelando, onTentarNovamente }: ProgressPanelProps) {
  const ativo = isJobActive(job.status);
  return (
    <section aria-label="Progresso da extração" className="flex flex-col gap-2 rounded-lg border p-4">
      {ativo && (
        <>
          <div className="flex items-center justify-between text-sm">
            <span>{job.step ?? (job.status === "queued" ? "Na fila..." : "Processando...")}</span>
            <span>{Math.round(job.progress)}%</span>
          </div>
          <Progress value={job.progress} aria-label="Progresso" />
          <Contadores job={job} />
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={onCancelar} disabled={cancelando}>
            Cancelar
          </Button>
        </>
      )}
      {job.status === "completed" && (
        <>
          <h3 className="font-medium">Extração concluída!</h3>
          <Resultado job={job} />
        </>
      )}
      {job.status === "completed_with_errors" && (
        <>
          <h3 className="font-medium text-amber-600">Extração concluída com avisos</h3>
          <Resultado job={job} />
        </>
      )}
      {job.status === "failed" && (
        <>
          <h3 className="font-medium text-destructive">A extração falhou</h3>
          {job.erro && <p className="text-sm">{job.erro}</p>}
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={onTentarNovamente}>
            Tentar novamente
          </Button>
        </>
      )}
      {job.status === "cancelled" && <p className="text-sm">Extração cancelada.</p>}
    </section>
  );
}
