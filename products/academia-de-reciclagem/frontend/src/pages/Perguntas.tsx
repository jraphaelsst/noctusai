/**
 * Perguntas abertas — `/perguntas` (contract §A.3, §B.3).
 *
 * List by `estado` (default `aberta`), an add form, and an answer form
 * that shows the `aviso` returned when `destino_kb` was set at creation
 * (the server does NOT write the KB entry — contract §B.3).
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
  Textarea,
} from "@noctusai/lib/design-system";
import { errorMessage } from "@/lib/errors";
import {
  useAnswerPergunta,
  useCreatePergunta,
  usePerguntasList,
  type OpenQuestion,
  type PerguntaEstado,
} from "@/hooks/usePerguntas";

export default function Perguntas() {
  const [estado, setEstado] = useState<PerguntaEstado>("aberta");
  const [createOpen, setCreateOpen] = useState(false);
  const [answering, setAnswering] = useState<OpenQuestion | null>(null);

  const { data, isPending, isFetching, error } = usePerguntasList(estado);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Perguntas abertas</h1>
          <p className="text-sm text-muted-foreground">
            Bloqueios e dúvidas que precisam de resposta.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          Nova pergunta
        </Button>
      </div>

      <div className="flex gap-2">
        {(["aberta", "respondida", "todas"] as PerguntaEstado[]).map((e) => (
          <Button key={e} variant={estado === e ? "primary" : "outline"} onClick={() => setEstado(e)}>
            {e === "aberta" ? "Abertas" : e === "respondida" ? "Respondidas" : "Todas"}
          </Button>
        ))}
      </div>

      {showSkeleton ? (
        <PageSkeleton />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma pergunta encontrada." />
      ) : (
        <div className="space-y-2">
          {data.items.map((q) => (
            <Card key={q.codigo} className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{q.codigo}</Badge>
                    <Badge variant={q.estado === "aberta" ? "default" : "muted"}>
                      {q.estado === "aberta" ? "Aberta" : "Respondida"}
                    </Badge>
                  </div>
                  <p className="mt-1 font-medium text-foreground">{q.pergunta}</p>
                  <p className="text-sm text-muted-foreground">Por que importa: {q.por_que_importa}</p>
                  <p className="text-sm text-muted-foreground">Bloqueia: {q.bloqueia}</p>
                  {q.destino_kb ? (
                    <p className="text-xs text-muted-foreground">Destino KB: {q.destino_kb}</p>
                  ) : null}
                  {q.resposta ? (
                    <p className="mt-2 rounded-md bg-muted/50 px-3 py-2 text-sm text-foreground">
                      {q.resposta}
                    </p>
                  ) : null}
                </div>
                {q.estado === "aberta" ? (
                  <Button variant="outline" onClick={() => setAnswering(q)}>
                    Responder
                  </Button>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}

      {createOpen ? <CreatePerguntaDialog onClose={() => setCreateOpen(false)} /> : null}
      {answering ? <AnswerDialog question={answering} onClose={() => setAnswering(null)} /> : null}
    </div>
  );
}

function CreatePerguntaDialog({ onClose }: { onClose: () => void }) {
  const [pergunta, setPergunta] = useState("");
  const [porQueImporta, setPorQueImporta] = useState("");
  const [bloqueia, setBloqueia] = useState("");
  const [destinoKb, setDestinoKb] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const createPergunta = useCreatePergunta();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createPergunta.mutate(
      {
        pergunta,
        por_que_importa: porQueImporta,
        bloqueia,
        destino_kb: destinoKb || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Pergunta registrada.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Nova pergunta" className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Nova pergunta</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Pergunta" required>
            <Textarea rows={2} value={pergunta} onChange={(e) => setPergunta(e.target.value)} required />
          </Field>
          <Field label="Por que importa" required>
            <Textarea
              rows={2}
              value={porQueImporta}
              onChange={(e) => setPorQueImporta(e.target.value)}
              required
            />
          </Field>
          <Field label="O que bloqueia" required>
            <Input value={bloqueia} onChange={(e) => setBloqueia(e.target.value)} required />
          </Field>
          <Field label="Destino na base de conhecimento (slug, opcional)">
            <Input value={destinoKb} onChange={(e) => setDestinoKb(e.target.value)} />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={createPergunta.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={createPergunta.isPending}>
            {createPergunta.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Registrar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function AnswerDialog({ question, onClose }: { question: OpenQuestion; onClose: () => void }) {
  const [resposta, setResposta] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const answerPergunta = useAnswerPergunta(question.codigo);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    answerPergunta.mutate(resposta, {
      onSuccess: (result) => {
        toast.success("Pergunta respondida.");
        if (result.aviso) {
          setAviso(result.aviso);
        } else {
          onClose();
        }
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  if (aviso) {
    return (
      <Dialog open onClose={onClose} title="Resposta registrada">
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Resposta registrada</h2>
        </DialogHeader>
        <DialogBody>
          <p className="text-sm text-foreground">{aviso}</p>
        </DialogBody>
        <DialogFooter>
          <Button variant="primary" onClick={onClose}>
            Entendi
          </Button>
        </DialogFooter>
      </Dialog>
    );
  }

  return (
    <Dialog open onClose={onClose} title={`Responder ${question.codigo}`} className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Responder {question.codigo}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-muted-foreground">{question.pergunta}</p>
          <Field label="Resposta" required>
            <Textarea rows={4} value={resposta} onChange={(e) => setResposta(e.target.value)} required />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={answerPergunta.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={answerPergunta.isPending}>
            {answerPergunta.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Responder
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
