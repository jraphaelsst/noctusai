/**
 * Decisões — `/decisoes` (contract §A.2, §B.2).
 *
 * List by `estado` + a detail dialog (fetched fresh via `GET
 * /api/decisions/{codigo}` — not derived from the list row, since the list
 * may be filtered/paginated away from the row by the time it's clicked).
 * "Registrar decisão" create form + "Substituir" (supersede) action. NO
 * edit, NO delete — decisions are append-only per contract §A.2.
 */
import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Select,
  Textarea,
} from "@noctusai/lib/design-system";
import { errorMessage } from "@/lib/errors";
import {
  useCreateDecisao,
  useDecisao,
  useDecisoesList,
  useSupersedeDecisao,
  type Decision,
  type DecisaoCreateInput,
  type DecisaoEstado,
} from "@/hooks/useDecisoes";

function estadoBadge(estado: DecisaoEstado) {
  return estado === "vigente" ? (
    <Badge variant="default">Vigente</Badge>
  ) : (
    <Badge variant="muted">Substituída</Badge>
  );
}

export default function Decisoes() {
  const [estado, setEstado] = useState<DecisaoEstado | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isPending, isFetching, error } = useDecisoesList(estado || undefined);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Decisões</h1>
          <p className="text-sm text-muted-foreground">
            Registro append-only de decisões do projeto.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          Registrar decisão
        </Button>
      </div>

      <Select value={estado} onChange={(e) => setEstado(e.target.value as DecisaoEstado | "")} className="sm:max-w-xs">
        <option value="">Todos os estados</option>
        <option value="vigente">Vigente</option>
        <option value="superseded">Substituída</option>
      </Select>

      {showSkeleton ? (
        <PageSkeleton />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma decisão encontrada." />
      ) : (
        <div className="space-y-2">
          {data.items.map((d) => (
            <button
              key={d.codigo}
              type="button"
              onClick={() => setSelected(d.codigo)}
              className="block w-full text-left"
            >
              <Card className="flex items-center justify-between gap-3 transition-colors hover:border-primary">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{d.codigo}</Badge>
                    <span className="font-semibold text-foreground">{d.titulo}</span>
                  </div>
                  <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{d.decisao}</p>
                </div>
                {estadoBadge(d.estado)}
              </Card>
            </button>
          ))}
        </div>
      )}

      {createOpen ? <CreateDecisaoDialog onClose={() => setCreateOpen(false)} /> : null}
      {selected ? <DecisaoDetailDialog codigo={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

function DecisaoFields({
  titulo,
  setTitulo,
  contexto,
  setContexto,
  decisao,
  setDecisao,
  alternativas,
  setAlternativas,
  relacionadas,
  setRelacionadas,
  motivo,
  setMotivo,
}: {
  titulo: string;
  setTitulo: (v: string) => void;
  contexto: string;
  setContexto: (v: string) => void;
  decisao: string;
  setDecisao: (v: string) => void;
  alternativas: string;
  setAlternativas: (v: string) => void;
  relacionadas: string;
  setRelacionadas: (v: string) => void;
  motivo: string;
  setMotivo: (v: string) => void;
}) {
  return (
    <>
      <Field label="Título" required>
        <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
      </Field>
      <Field label="Contexto">
        <Textarea rows={2} value={contexto} onChange={(e) => setContexto(e.target.value)} />
      </Field>
      <Field label="Decisão" required>
        <Textarea rows={3} value={decisao} onChange={(e) => setDecisao(e.target.value)} required />
      </Field>
      <Field label="Alternativas rejeitadas">
        <Textarea rows={2} value={alternativas} onChange={(e) => setAlternativas(e.target.value)} />
      </Field>
      <Field label="Relacionadas (códigos separados por vírgula)">
        <Input
          value={relacionadas}
          onChange={(e) => setRelacionadas(e.target.value)}
          placeholder="ex: D-10, D-12"
        />
      </Field>
      <Field label="Motivo" required>
        <Textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} required />
      </Field>
    </>
  );
}

function useDecisaoForm() {
  const [titulo, setTitulo] = useState("");
  const [contexto, setContexto] = useState("");
  const [decisao, setDecisao] = useState("");
  const [alternativas, setAlternativas] = useState("");
  const [relacionadas, setRelacionadas] = useState("");
  const [motivo, setMotivo] = useState("");

  function toPayload(): DecisaoCreateInput {
    return {
      titulo,
      decisao,
      motivo,
      contexto: contexto || undefined,
      alternativas_rejeitadas: alternativas || undefined,
      relacionadas: relacionadas
        ? relacionadas.split(",").map((r) => r.trim()).filter(Boolean)
        : undefined,
    };
  }

  return {
    fieldsProps: { titulo, setTitulo, contexto, setContexto, decisao, setDecisao, alternativas, setAlternativas, relacionadas, setRelacionadas, motivo, setMotivo },
    toPayload,
  };
}

function CreateDecisaoDialog({ onClose }: { onClose: () => void }) {
  const { fieldsProps, toPayload } = useDecisaoForm();
  const [formError, setFormError] = useState<string | null>(null);
  const createDecisao = useCreateDecisao();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createDecisao.mutate(toPayload(), {
      onSuccess: () => {
        toast.success("Decisão registrada.");
        onClose();
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  return (
    <Dialog open onClose={onClose} title="Registrar decisão" className="max-w-2xl">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Registrar decisão</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <DecisaoFields {...fieldsProps} />
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={createDecisao.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={createDecisao.isPending}>
            {createDecisao.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Registrar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function DecisaoDetailDialog({ codigo, onClose }: { codigo: string; onClose: () => void }) {
  const { data, isPending, error } = useDecisao(codigo);
  const [supersedeOpen, setSupersedeOpen] = useState(false);

  return (
    <Dialog open onClose={onClose} title={codigo} className="max-w-2xl">
      <DialogHeader>
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-foreground">{codigo}</h2>
          {data ? estadoBadge(data.estado) : null}
        </div>
      </DialogHeader>
      <DialogBody className="space-y-3">
        {isPending && !data ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : error ? (
          <ErrorState message={errorMessage(error)} />
        ) : !data ? null : (
          <DecisaoDetailBody decision={data} />
        )}
      </DialogBody>
      <DialogFooter>
        {data && data.estado === "vigente" ? (
          <Button variant="primary" onClick={() => setSupersedeOpen(true)}>
            Substituir
          </Button>
        ) : null}
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
      {supersedeOpen ? (
        <SupersedeDialog codigo={codigo} onClose={() => setSupersedeOpen(false)} onDone={onClose} />
      ) : null}
    </Dialog>
  );
}

function DecisaoDetailBody({ decision }: { decision: Decision }) {
  return (
    <div className="space-y-3 text-sm">
      <div>
        <h3 className="font-semibold text-foreground">{decision.titulo}</h3>
        <p className="text-xs text-muted-foreground">{decision.data}</p>
      </div>
      {decision.contexto ? (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Contexto</p>
          <p className="text-foreground">{decision.contexto}</p>
        </div>
      ) : null}
      <div>
        <p className="text-xs font-medium text-muted-foreground">Decisão</p>
        <p className="text-foreground">{decision.decisao}</p>
      </div>
      <div>
        <p className="text-xs font-medium text-muted-foreground">Motivo</p>
        <p className="text-foreground">{decision.motivo}</p>
      </div>
      {decision.alternativas_rejeitadas ? (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Alternativas rejeitadas</p>
          <p className="text-foreground">{decision.alternativas_rejeitadas}</p>
        </div>
      ) : null}
      {decision.substitui ? (
        <p className="text-xs text-muted-foreground">Substitui: {decision.substitui}</p>
      ) : null}
      {decision.superseded_by ? (
        <p className="text-xs text-muted-foreground">Substituída por: {decision.superseded_by}</p>
      ) : null}
      {decision.relacionadas.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {decision.relacionadas.map((r) => (
            <Badge key={r} variant="outline">
              {r}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SupersedeDialog({
  codigo,
  onClose,
  onDone,
}: {
  codigo: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { fieldsProps, toPayload } = useDecisaoForm();
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<{ nova: Decision; substituida: Decision } | null>(null);
  const supersede = useSupersedeDecisao(codigo);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    supersede.mutate(toPayload(), {
      onSuccess: (data) => {
        toast.success(`${data.nova.codigo} substitui ${data.substituida.codigo}.`);
        setResult(data);
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  if (result) {
    return (
      <Dialog open onClose={onDone} title="Decisão substituída" className="max-w-2xl">
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Decisão substituída</h2>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Nova decisão</p>
            <DecisaoDetailBody decision={result.nova} />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Decisão substituída</p>
            <DecisaoDetailBody decision={result.substituida} />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="primary" onClick={onDone}>
            Concluir
          </Button>
        </DialogFooter>
      </Dialog>
    );
  }

  return (
    <Dialog open onClose={onClose} title={`Substituir ${codigo}`} className="max-w-2xl">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Substituir {codigo}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-muted-foreground">
            Cria uma nova decisão que substitui {codigo}; {codigo} passa a "Substituída".
          </p>
          <DecisaoFields {...fieldsProps} />
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={supersede.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={supersede.isPending}>
            {supersede.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Substituir
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
