/**
 * `ConsentHubPage` — public hub at `/consent`.
 * Lists the platform's legal documents. Auto-routed by `createProductApp`
 * for every product (seed-first, no auth). Doubles as the canonical landing
 * referenced from Google OAuth verification and Meta App Review.
 */
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { CONSENT_META, CONSENT_DOCS } from "../../content/consent";

const DOC_BLURB: Record<string, string> = {
  "privacy-policy":
    "Como coletamos, usamos, compartilhamos e protegemos dados pessoais (LGPD), incluindo as integrações com Google e Meta/WhatsApp.",
  "terms-of-use":
    "Regras de acesso e uso da plataforma, integrações de terceiros, recursos de IA e responsabilidades.",
};

export function ConsentHubPage() {
  useEffect(() => {
    const prev = document.title;
    document.title = `Documentos legais — ${CONSENT_META.platform}`;
    return () => {
      document.title = prev;
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="mx-auto max-w-2xl px-5 py-16">
        <div className="flex items-center gap-3">
          <svg width="44" height="44" viewBox="0 0 100 100" aria-hidden="true" className="shrink-0">
            <rect x="4" y="4" width="92" height="92" rx="22" fill="#16181d" />
            <path d="M74 22 a16 16 0 1 0 9 29 a13 13 0 1 1 -9 -29 Z" fill="#2c303a" />
            <circle cx="40" cy="56" r="15" fill="none" stroke="#9aa0ad" strokeWidth="4" />
            <circle cx="68" cy="56" r="15" fill="none" stroke="#9aa0ad" strokeWidth="4" />
            <circle cx="40" cy="56" r="4" fill="#eef0f5" />
            <circle cx="68" cy="56" r="4" fill="#eef0f5" />
            <path d="M30 40 Q 47 28 54 42 Q 61 28 78 40" fill="none" stroke="#9aa0ad" strokeWidth="3.5" strokeLinecap="round" />
          </svg>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Noctus<span className="text-muted-foreground">AI</span>
            </h1>
            <p className="text-sm text-muted-foreground">Documentos legais</p>
          </div>
        </div>

        <p className="mt-6 text-[0.95rem] leading-relaxed text-foreground/80">
          Estes documentos regem o uso da plataforma NoctusAI e o tratamento de
          dados pessoais, em conformidade com a LGPD (Lei nº 13.709/2018).
        </p>

        <div className="mt-8 space-y-3">
          {CONSENT_DOCS.map((d) => (
            <Link
              key={d.slug}
              to={`/consent/${d.slug}`}
              className="block rounded-lg border border-border bg-card p-5 transition-colors hover:bg-accent/60"
            >
              <h2 className="text-base font-semibold tracking-tight">{d.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{DOC_BLURB[d.slug]}</p>
            </Link>
          ))}
        </div>

        <footer className="mt-10 border-t border-border pt-6 text-sm text-muted-foreground">
          <p>
            Encarregado (DPO): {CONSENT_META.dpoName} ·{" "}
            <a className="underline underline-offset-2" href={`mailto:${CONSENT_META.email}`}>
              {CONSENT_META.email}
            </a>
          </p>
          <p className="mt-1">
            Versão {CONSENT_META.version} · Última atualização {CONSENT_META.lastUpdated}
          </p>
        </footer>
      </main>
    </div>
  );
}

export default ConsentHubPage;
