/**
 * Landing — `/` for a visitor with no session (ninho-vazio CONTRACT.md
 * §Frontend FE-B: "Landing copy re-themed to Ninho Vazio").
 *
 * Audience: women 50+ whose children left home, with Mônica Tangerino,
 * psicanalista. Calm, large type, one clear action (`/cadastro`). The tiers
 * render from `GET /api/planos/publicos` (names/prices are data, never
 * hardcoded); the care line closes the page.
 */
import { Link } from "react-router-dom";
import { ArrowRight, Feather } from "lucide-react";

import { LinhaDeCuidado } from "@/components/LinhaDeCuidado";
import { BOTAO_PRIMARIO, BOTAO_SECUNDARIO } from "@/components/PortalShell";
import { usePlanosPublicos } from "@/hooks/usePlanosPublicos";
import { precoPorCiclo } from "@/lib/ninhoVazio";

function Planos() {
  const { data, isPending, error } = usePlanosPublicos();
  const showSkeleton = isPending && !data;
  const planos = [...(data?.items ?? [])].sort((a, b) => a.preco_centavos - b.preco_centavos);

  if (showSkeleton) {
    return (
      <div className="grid gap-4 sm:grid-cols-3" data-testid="landing-planos-skeleton">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-44 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  }
  if (!data && error) {
    return (
      <p className="text-center text-lg text-muted-foreground">
        Não conseguimos mostrar os planos agora. Você pode criar sua conta gratuita e escolher depois.
      </p>
    );
  }
  if (planos.length === 0) {
    return (
      <p className="text-center text-lg text-muted-foreground">
        Você começa gratuitamente. Os planos aparecem aqui em breve.
      </p>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {planos.map((p) => (
        <article key={p.id} className="flex flex-col rounded-xl border border-border bg-card p-6">
          <h3 className="text-xl font-semibold text-foreground">{p.nome}</h3>
          <p className="mt-1 text-lg text-primary">{precoPorCiclo(p.preco_centavos, p.ciclo)}</p>
          {p.descricao ? <p className="mt-3 flex-1 text-base text-muted-foreground">{p.descricao}</p> : <div className="flex-1" />}
        </article>
      ))}
    </div>
  );
}

export default function Landing() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-base leading-relaxed">
      <header className="flex h-20 items-center justify-between border-b border-border bg-card px-4 sm:px-8">
        <Link to="/" className="flex items-center gap-2">
          <Feather className="h-7 w-7 text-primary" aria-hidden="true" />
          <span className="text-xl font-semibold text-primary">Ninho Vazio</span>
        </Link>
        <Link to="/login" className={BOTAO_SECUNDARIO}>
          Entrar
        </Link>
      </header>

      <main className="flex-1">
        <section className="bg-gradient-to-b from-primary/5 to-background px-4 py-16 text-center sm:py-24">
          <div className="mx-auto max-w-3xl space-y-6">
            <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              Quando os filhos saem de casa, a vida pede um novo lugar.
            </h1>
            <p className="mx-auto max-w-2xl text-xl text-muted-foreground">
              Criar é preparar para ir. Aqui, com a psicanalista Mônica Tangerino e outras mulheres que vivem o
              mesmo momento, você atravessa essa passagem sem pressa — e reencontra a si mesma.
            </p>
            <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
              <Link to="/cadastro" className={BOTAO_PRIMARIO}>
                Criar minha conta
                <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </Link>
              <Link to="/login" className={BOTAO_SECUNDARIO}>
                Já tenho conta
              </Link>
            </div>
          </div>
        </section>

        <section className="px-4 py-14">
          <div className="mx-auto grid max-w-5xl gap-8 sm:grid-cols-3">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-foreground">A travessia</h2>
              <p className="text-lg text-muted-foreground">
                Perder um lugar dói. Conteúdos e reflexões para entender o que está acontecendo com você.
              </p>
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-foreground">As grupoterapias</h2>
              <p className="text-lg text-muted-foreground">
                Encontros ao vivo conduzidos pela Mônica. Você pode assistir ou, se quiser, ter a sua vez de fala.
              </p>
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-foreground">O reencontro</h2>
              <p className="text-lg text-muted-foreground">
                Um espaço seguro e respeitoso, com mulheres que entendem — para voltar a olhar para os seus desejos.
              </p>
            </div>
          </div>
        </section>

        <section className="bg-muted/30 px-4 py-14" aria-labelledby="planos">
          <div className="mx-auto max-w-5xl space-y-8">
            <div className="space-y-2 text-center">
              <h2 id="planos" className="text-3xl font-semibold text-foreground">
                Escolha como participar
              </h2>
              <p className="text-lg text-muted-foreground">Você pode começar grátis e mudar quando quiser.</p>
            </div>
            <Planos />
            <div className="flex justify-center">
              <Link to="/cadastro" className={BOTAO_PRIMARIO}>
                Criar minha conta
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="mt-auto border-t bg-card px-4 py-8">
        <div className="mx-auto max-w-5xl space-y-4">
          <LinhaDeCuidado className="text-base" />
          <div className="flex flex-col items-center justify-between gap-2 text-sm text-muted-foreground sm:flex-row">
            <span>Ninho Vazio · Mônica Tangerino</span>
            <span className="flex gap-4">
              <Link to="/consent/terms-of-use" className="underline underline-offset-2">Termos de uso</Link>
              <Link to="/consent/privacy-policy" className="underline underline-offset-2">Privacidade</Link>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
