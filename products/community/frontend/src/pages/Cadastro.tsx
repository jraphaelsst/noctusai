/**
 * Cadastro — `/cadastro`, the PUBLIC signup (ninho-vazio CONTRACT.md
 * §Identity `POST /api/cadastro` + §Frontend FE-B).
 *
 * Registered as a `publicRoute` (no auth, no Layout — same seam as
 * `/assinar`). Everyone is registered on the free plan server-side; the
 * tier picker records what the visitor WANTS so that, if it is a paid
 * tier, the success screen's "Entrar" goes to `/login?plano=<id>` and the
 * login page forwards to `/portal?trocar=<id>` (the member's plan change
 * dialog opens for that tier).
 *
 * Tier names and prices render from `GET /api/planos/publicos` — never
 * hardcoded. Turnstile reuses `components/TurnstileWidget` (shared with
 * `/assinar`). Every backend error (400 terms, 403 Turnstile, 409 existing
 * e-mail / no free plan, 429) is shown verbatim.
 */
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Feather } from "lucide-react";
import { Button, Input } from "@noctusai/lib/design-system";

import { Card, ErrorState, Field, FormError } from "@/components/FormControls";
import { LinhaDeCuidado } from "@/components/LinhaDeCuidado";
import { BOTAO_PRIMARIO } from "@/components/PortalShell";
import { TurnstileWidget } from "@/components/TurnstileWidget";
import { SENHA_MAX, SENHA_MIN, TELEFONE_RE, useCadastro } from "@/hooks/useCadastro";
import { ordenarPlanosPublicos, usePlanosPublicos, type PlanoPublico } from "@/hooks/usePlanosPublicos";
import { errorMessage } from "@/lib/errors";
import { NIVEL_DESCRICAO, precoPorCiclo } from "@/lib/ninhoVazio";

const INPUT_GRANDE = "h-12 text-base";

/** The free tier = the cheapest public plan priced at zero. */
function planoGratuito(planos: PlanoPublico[]): PlanoPublico | undefined {
  return planos.find((p) => p.preco_centavos === 0);
}

/** Where "Entrar" leads after signup: straight to checkout for a paid tier. */
export function destinoAposCadastro(plano: PlanoPublico | undefined): string {
  if (!plano || plano.preco_centavos === 0) return "/login";
  return `/login?plano=${encodeURIComponent(plano.id)}`;
}

function Sucesso({ nome, plano }: { nome: string; plano: PlanoPublico | undefined }) {
  const pago = !!plano && plano.preco_centavos > 0;
  return (
    <div className="space-y-5 text-center" data-testid="cadastro-sucesso">
      <CheckCircle2 className="mx-auto h-12 w-12 text-primary" aria-hidden="true" />
      <h1 className="text-2xl font-semibold text-foreground">Que bom ter você aqui, {nome.split(" ")[0]}.</h1>
      <p className="text-lg text-muted-foreground">
        Seu cadastro está pronto. Entre com o seu e-mail e a senha que você escolheu.
      </p>
      {pago && plano ? (
        <p className="text-lg text-foreground">
          Depois de entrar, levamos você direto para ativar o plano <strong>{plano.nome}</strong>.
        </p>
      ) : null}
      <Link to={destinoAposCadastro(plano)} className={`${BOTAO_PRIMARIO} w-full`}>
        Entrar
      </Link>
      <LinhaDeCuidado className="text-left text-base" />
    </div>
  );
}

export default function Cadastro() {
  const planosQuery = usePlanosPublicos();
  const cadastro = useCadastro();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [telefone, setTelefone] = useState("");
  const [senha, setSenha] = useState("");
  const [aceite, setAceite] = useState(false);
  const [planoId, setPlanoId] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [concluido, setConcluido] = useState(false);

  const planos = useMemo(
    () => ordenarPlanosPublicos(planosQuery.data?.items ?? []),
    [planosQuery.data],
  );
  const showSkeleton = planosQuery.isPending && !planosQuery.data;
  // The picked tier, defaulting to the free one until the visitor chooses.
  const planoEscolhido = planos.find((p) => p.id === planoId) ?? planoGratuito(planos);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (senha.length < SENHA_MIN || senha.length > SENHA_MAX) {
      setFormError(`A senha precisa ter entre ${SENHA_MIN} e ${SENHA_MAX} caracteres.`);
      return;
    }
    const tel = telefone.trim();
    if (tel && !TELEFONE_RE.test(tel)) {
      setFormError("Informe o telefone com DDI e DDD, só números. Exemplo: +5511999999999.");
      return;
    }
    if (!aceite) {
      setFormError("É preciso aceitar os termos.");
      return;
    }
    cadastro.mutate(
      {
        nome: nome.trim(),
        email: email.trim(),
        telefone: tel || null,
        senha,
        turnstile_token: turnstileToken,
        aceite_termos: aceite,
      },
      {
        onSuccess: () => setConcluido(true),
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="mx-auto w-full max-w-xl">
        <Link to="/" className="mb-6 inline-flex items-center gap-2 text-lg font-semibold text-primary">
          <Feather className="h-6 w-6" aria-hidden="true" />
          Ninho Vazio
        </Link>
        <Card className="p-6 sm:p-8">
          {concluido ? (
            <Sucesso nome={nome} plano={planoEscolhido} />
          ) : (
            <>
              <h1 className="text-2xl font-semibold text-foreground sm:text-3xl">Criar minha conta</h1>
              <p className="mt-2 text-lg text-muted-foreground">
                Um lugar para a travessia de quando os filhos saem de casa — no seu tempo.
              </p>
              <form onSubmit={handleSubmit} className="mt-6 space-y-5 text-base">
                <FormError message={formError} />

                <fieldset className="space-y-3">
                  <legend className="mb-2 text-base font-medium text-foreground">Como você quer participar?</legend>
                  {showSkeleton ? (
                    <div className="space-y-3" data-testid="cadastro-planos-skeleton">
                      {[1, 2, 3].map((i) => (
                        <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
                      ))}
                    </div>
                  ) : planosQuery.error && !planosQuery.data ? (
                    <ErrorState message={errorMessage(planosQuery.error)} />
                  ) : planos.length === 0 ? (
                    <p className="text-base text-muted-foreground">
                      Você começa no plano gratuito. Os outros planos aparecem aqui em breve.
                    </p>
                  ) : (
                    planos.map((p) => (
                      <label
                        key={p.id}
                        className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-4 has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                      >
                        <input
                          type="radio"
                          name="plano"
                          value={p.id}
                          checked={planoEscolhido?.id === p.id}
                          onChange={() => setPlanoId(p.id)}
                          className="mt-1 h-5 w-5"
                        />
                        <span>
                          <span className="block text-lg font-medium text-foreground">
                            {p.nome} · {precoPorCiclo(p.preco_centavos, p.ciclo)}
                          </span>
                          <span className="block text-base text-foreground" data-testid={`cadastro-nivel-${p.id}`}>
                            {NIVEL_DESCRICAO[p.nivel_grupoterapia]}
                          </span>
                          {p.descricao ? (
                            <span className="block text-base text-muted-foreground">{p.descricao}</span>
                          ) : null}
                        </span>
                      </label>
                    ))
                  )}
                  {planoEscolhido && planoEscolhido.preco_centavos > 0 ? (
                    <p className="text-base text-muted-foreground">
                      Primeiro criamos sua conta; o pagamento vem logo depois de entrar.
                    </p>
                  ) : null}
                </fieldset>

                <Field label="Seu nome" required>
                  <Input className={INPUT_GRANDE} value={nome} onChange={(e) => setNome(e.target.value)} maxLength={120} required autoComplete="name" />
                </Field>
                <Field label="E-mail" required>
                  <Input className={INPUT_GRANDE} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
                </Field>
                <Field label="Telefone (opcional)" help="Com DDI e DDD, ex: +5511999999999">
                  <Input className={INPUT_GRANDE} value={telefone} onChange={(e) => setTelefone(e.target.value)} placeholder="+5511999999999" inputMode="tel" autoComplete="tel" />
                </Field>
                <Field label="Crie uma senha" required help={`De ${SENHA_MIN} a ${SENHA_MAX} caracteres.`}>
                  <Input className={INPUT_GRANDE} type="password" value={senha} onChange={(e) => setSenha(e.target.value)} required autoComplete="new-password" />
                </Field>

                <label className="flex items-start gap-3 text-base text-foreground">
                  <input type="checkbox" checked={aceite} onChange={(e) => setAceite(e.target.checked)} className="mt-1 h-5 w-5" />
                  <span>
                    Li e aceito os{" "}
                    <a href="/consent/terms-of-use" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
                      termos de uso
                    </a>{" "}
                    e a{" "}
                    <a href="/consent/privacy-policy" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
                      política de privacidade
                    </a>
                    .
                  </span>
                </label>

                <TurnstileWidget onVerify={setTurnstileToken} onExpire={() => setTurnstileToken("")} />

                <Button
                  type="submit"
                  variant="primary"
                  className="h-12 w-full text-base"
                  disabled={cadastro.isPending || !turnstileToken}
                >
                  {cadastro.isPending ? "Criando sua conta…" : "Criar minha conta"}
                </Button>
                <p className="text-center text-base text-muted-foreground">
                  Já tem cadastro?{" "}
                  <Link to="/login" className="font-medium text-primary underline underline-offset-2">
                    Entrar
                  </Link>
                </p>
              </form>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
