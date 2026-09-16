/**
 * Inscrever — `/inscrever` (community-m1-contract.md §Frontend), the
 * PUBLIC application form.
 *
 * Registered as a `publicRoute` in `App.tsx` (`createProductApp`'s
 * `publicRoutes` config) — rendered WITHOUT the seed `Layout`/auth gate,
 * so a visitor with no session can reach and submit it. Renders
 * `GET /api/aplicacoes/formulario` (public, `ativa=true` only) and submits
 * `POST /api/aplicacoes` (public). Both calls go through the shared `api`
 * client unauthenticated by construction — `getAuthToken()` returning
 * `null` omits the Authorization header instead of failing
 * (`seed/lib/frontend/src/api.ts`).
 *
 * Question types render per `tipo`: texto → input, texto_longo →
 * textarea, escolha_unica → radio group, escolha_multipla → checkbox
 * group (answer is a string[]), booleano → yes/no select.
 */
import { useState, type FormEvent } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button, Input } from "@noctusai/lib/design-system";
import { Card, ErrorState, Field, FormError, Select, Textarea } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useFormulario, useSubmitAplicacao, type Pergunta } from "@/hooks/useAplicacoes";

function QuestionField({
  pergunta,
  value,
  onChange,
}: {
  pergunta: Pergunta;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  switch (pergunta.tipo) {
    case "texto_longo":
      return (
        <Textarea
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          required={pergunta.obrigatoria}
          rows={3}
        />
      );
    case "escolha_unica":
      return (
        <div className="space-y-1.5">
          {pergunta.opcoes.map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="radio"
                name={pergunta.id}
                value={opt}
                checked={value === opt}
                onChange={() => onChange(opt)}
                required={pergunta.obrigatoria}
              />
              {opt}
            </label>
          ))}
        </div>
      );
    case "escolha_multipla": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="space-y-1.5">
          {pergunta.opcoes.map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={(e) =>
                  onChange(e.target.checked ? [...selected, opt] : selected.filter((o) => o !== opt))
                }
              />
              {opt}
            </label>
          ))}
        </div>
      );
    }
    case "booleano":
      return (
        <Select
          value={value === true ? "sim" : value === false ? "nao" : ""}
          onChange={(e) => onChange(e.target.value === "sim")}
          required={pergunta.obrigatoria}
        >
          <option value="" disabled>
            Selecione...
          </option>
          <option value="sim">Sim</option>
          <option value="nao">Não</option>
        </Select>
      );
    case "texto":
    default:
      return (
        <Input
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          required={pergunta.obrigatoria}
        />
      );
  }
}

export default function Inscrever() {
  const { data, isPending, error } = useFormulario();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [telefone, setTelefone] = useState("");
  const [respostas, setRespostas] = useState<Record<string, unknown>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const submit = useSubmitAplicacao();

  const showSkeleton = isPending && !data;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    submit.mutate(
      { nome, email, telefone: telefone || null, respostas },
      {
        onSuccess: () => setSuccess(true),
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-lg">
        <Card>
          <h1 className="text-xl font-bold text-foreground">Inscreva-se</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Preencha o formulário abaixo para se candidatar à comunidade.
          </p>

          {showSkeleton ? (
            <div className="mt-6 space-y-3" data-testid="inscrever-skeleton">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : error ? (
            <div className="mt-6">
              <ErrorState message={errorMessage(error)} />
            </div>
          ) : success ? (
            <div className="mt-6 flex flex-col items-center gap-2 py-8 text-center" data-testid="inscrever-success">
              <CheckCircle2 className="h-10 w-10 text-primary" />
              <p className="font-medium text-foreground">Inscrição enviada!</p>
              <p className="text-sm text-muted-foreground">
                Recebemos sua inscrição e vamos analisá-la em breve.
              </p>
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="mt-6">
              <ErrorState message="O formulário de inscrição não está disponível no momento." />
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <FormError message={formError} />
              <Field label="Nome" required>
                <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
              </Field>
              <Field label="E-mail" required>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="Telefone" help="Opcional. Formato internacional, ex: +5511999999999">
                <Input value={telefone} onChange={(e) => setTelefone(e.target.value)} placeholder="+5511999999999" />
              </Field>
              {data.items.map((p) => (
                <Field key={p.id} label={p.pergunta} required={p.obrigatoria}>
                  <QuestionField
                    pergunta={p}
                    value={respostas[p.id]}
                    onChange={(value) => setRespostas((prev) => ({ ...prev, [p.id]: value }))}
                  />
                </Field>
              ))}
              <Button type="submit" variant="primary" disabled={submit.isPending} className="w-full">
                {submit.isPending ? "Enviando..." : "Enviar inscrição"}
              </Button>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
