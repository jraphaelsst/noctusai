/** Upload of brand material (multiple files, optional description each) + job progress. */
import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button, Input } from '@noctusai/lib/design-system';

import { useBrandJob, useIngestBrand } from '../../hooks/useBrandIdentity';
import { ACCEPT_ATTR, validateBrandFiles } from '../../lib/brand-contract';
import { teamErrorMessage } from '../../lib/team-errors';

const JOB_LABEL = { queued: 'Na fila…', running: 'Lendo o material e extraindo a identidade…', done: 'Pronto', failed: 'Falhou' } as const;

export function BrandUpload({
  jobId, onJobStarted,
}: { jobId: string | null; onJobStarted: (jobId: string) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [refusals, setRefusals] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const ingest = useIngestBrand();
  const job = useBrandJob(jobId);
  const busy = ingest.isPending || job.data?.status === 'queued' || job.data?.status === 'running';

  function pick(list: FileList | null) {
    const incoming = Array.from(list ?? []);
    const errors = validateBrandFiles(files, incoming);
    const bad = new Set(errors.map((e) => e.split('"')[1]));
    setRefusals(errors);
    setFiles((cur) => [...cur, ...incoming.filter((f) => !bad.has(f.name))]);
    if (inputRef.current) inputRef.current.value = '';
  }

  function submit() {
    ingest.mutate({ files, descriptions }, {
      onSuccess: (res) => {
        onJobStarted(res.job_id);
        setFiles([]);
        setDescriptions({});
        toast.success('Material enviado. Gerando o rascunho…');
      },
      onError: (err) => toast.error(teamErrorMessage(err, 'Não foi possível enviar o material')),
    });
  }

  return (
    <div className="space-y-3" data-testid="brand-upload">
      <p className="text-sm text-muted-foreground">
        Envie o manual da marca, logos e fontes (md, pdf, png, jpg, webp, woff2 — até 10 arquivos, 10 MB cada, 25 MB no total).
        A IA extrai cores, fontes e voz e cria um rascunho que você revisa antes de ativar.
      </p>
      <input
        ref={inputRef} type="file" multiple accept={ACCEPT_ATTR} className="hidden" data-testid="brand-file-input"
        onChange={(e) => pick(e.target.files)}
      />
      <Button variant="outline" onClick={() => inputRef.current?.click()} disabled={busy}>Escolher arquivos</Button>

      {refusals.length > 0 && (
        <ul role="alert" className="space-y-0.5 text-xs text-destructive">
          {refusals.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f) => (
            <li key={f.name} className="flex items-center gap-2 rounded-md border border-border bg-card p-2">
              <span className="w-48 truncate text-sm text-foreground" title={f.name}>{f.name}</span>
              <Input
                aria-label={`Descrição de ${f.name}`} placeholder="Descrição (opcional) — ex.: logo para fundo escuro"
                value={descriptions[f.name] ?? ''}
                onChange={(e) => setDescriptions((d) => ({ ...d, [f.name]: e.target.value }))}
              />
              <Button variant="ghost" onClick={() => setFiles((cur) => cur.filter((x) => x !== f))}>Remover</Button>
            </li>
          ))}
        </ul>
      )}

      <Button onClick={submit} disabled={files.length === 0 || busy}>
        {ingest.isPending ? 'Enviando…' : 'Gerar identidade'}
      </Button>

      {jobId && job.data && (
        <p
          role={job.data.status === 'failed' ? 'alert' : 'status'} data-testid="brand-job-status"
          className={job.data.status === 'failed' ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'}
        >
          {JOB_LABEL[job.data.status]}
          {job.data.status === 'failed' && job.data.error ? `: ${job.data.error}` : ''}
        </p>
      )}
      {jobId && job.isError && !job.data && (
        <p role="alert" className="text-sm text-destructive">Não foi possível acompanhar o processamento.{' '}
          <button className="underline" onClick={() => job.refetch()}>Tentar de novo</button>
        </p>
      )}
    </div>
  );
}
