/**
 * `ConsentDocLayout` — the public, unauthenticated shell that renders a single
 * legal document (Política de Privacidade or Termos de Uso).
 *
 * Mounted by `createProductApp` at `/consent/privacy-policy` and
 * `/consent/terms-of-use` for EVERY product (seed-first; no per-product code).
 * Renders WITHOUT the app Layout and WITHOUT auth so Google's and Meta's
 * verification crawlers can reach it. Content comes from `content/consent.ts`.
 */
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { CONSENT_META, CONSENT_DOCS, type ConsentDoc, type DocBlock } from "../../content/consent";

function Block({ block }: { block: DocBlock }) {
  if ("ul" in block) {
    return (
      <ul className="my-3 list-disc space-y-1.5 pl-6 text-[0.95rem] leading-relaxed text-foreground/90">
        {block.ul.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    );
  }
  return <p className="my-3 text-[0.95rem] leading-relaxed text-foreground/90">{block.p}</p>;
}

function NoctusMark() {
  // Compact echo of the platform logo: two watchful eye-nodes + a crescent.
  return (
    <svg width="34" height="34" viewBox="0 0 100 100" aria-hidden="true" className="shrink-0">
      <rect x="4" y="4" width="92" height="92" rx="22" fill="#16181d" />
      <path d="M74 22 a16 16 0 1 0 9 29 a13 13 0 1 1 -9 -29 Z" fill="#2c303a" />
      <circle cx="40" cy="56" r="15" fill="none" stroke="#9aa0ad" strokeWidth="4" />
      <circle cx="68" cy="56" r="15" fill="none" stroke="#9aa0ad" strokeWidth="4" />
      <circle cx="40" cy="56" r="4" fill="#eef0f5" />
      <circle cx="68" cy="56" r="4" fill="#eef0f5" />
      <path d="M30 40 Q 47 28 54 42 Q 61 28 78 40" fill="none" stroke="#9aa0ad" strokeWidth="3.5" strokeLinecap="round" />
    </svg>
  );
}

export function ConsentDocLayout({ doc }: { doc: ConsentDoc }) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${doc.title} — ${CONSENT_META.platform}`;
    return () => {
      document.title = prev;
    };
  }, [doc.title]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Top bar */}
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-4">
          <Link to="/consent" className="flex items-center gap-2.5">
            <NoctusMark />
            <span className="text-lg font-semibold tracking-tight">
              Noctus<span className="text-muted-foreground">AI</span>
            </span>
          </Link>
          <span className="text-xs uppercase tracking-widest text-muted-foreground">
            Documentos legais
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-10">
        {/* Doc switcher */}
        <nav className="mb-8 flex flex-wrap gap-2" aria-label="Documentos">
          {CONSENT_DOCS.map((d) => {
            const active = d.slug === doc.slug;
            return (
              <Link
                key={d.slug}
                to={`/consent/${d.slug}`}
                aria-current={active ? "page" : undefined}
                className={
                  "rounded-md border px-3 py-1.5 text-sm transition-colors " +
                  (active
                    ? "border-foreground/20 bg-accent font-medium text-foreground"
                    : "border-border text-muted-foreground hover:bg-accent/60")
                }
              >
                {d.shortLabel}
              </Link>
            );
          })}
        </nav>

        {/* Title + metadata */}
        <h1 className="text-3xl font-semibold tracking-tight">{doc.title}</h1>
        <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-1 text-sm text-muted-foreground sm:grid-cols-2">
          <div>
            <span className="font-medium text-foreground/80">Controlador:</span>{" "}
            {CONSENT_META.controllerName} ({CONSENT_META.controllerLocation})
          </div>
          <div>
            <span className="font-medium text-foreground/80">Versão:</span> {CONSENT_META.version}
          </div>
          <div>
            <span className="font-medium text-foreground/80">Última atualização:</span>{" "}
            {CONSENT_META.lastUpdated}
          </div>
          <div>
            <span className="font-medium text-foreground/80">Plataforma:</span>{" "}
            {CONSENT_META.platform}
          </div>
        </dl>

        <p className="mt-6 border-l-2 border-border pl-4 text-[0.95rem] leading-relaxed text-foreground/80">
          {doc.intro}
        </p>

        {/* Sections (ABNT NBR 6024 progressive numbering) */}
        <div className="mt-8 space-y-8">
          {doc.sections.map((s) => (
            <section key={s.n} id={`sec-${s.n}`} className="scroll-mt-20">
              <h2 className="text-lg font-semibold tracking-tight">
                <span className="text-muted-foreground">{s.n}.</span> {s.title}
              </h2>
              {s.blocks.map((b, i) => (
                <Block key={i} block={b} />
              ))}
            </section>
          ))}
        </div>

        {/* Contact / DPO */}
        <section className="mt-12 rounded-lg border border-border bg-card p-5">
          <h2 className="text-base font-semibold tracking-tight">Encarregado (DPO) e contato</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {CONSENT_META.dpoName} — {CONSENT_META.controllerKind}.
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            <li>
              <span className="text-muted-foreground">E-mail:</span>{" "}
              <a className="font-medium underline underline-offset-2" href={`mailto:${CONSENT_META.email}`}>
                {CONSENT_META.email}
              </a>
            </li>
            <li>
              <span className="text-muted-foreground">Telefone/WhatsApp:</span>{" "}
              <a
                className="font-medium underline underline-offset-2"
                href={`tel:${CONSENT_META.phone.replace(/[^+\d]/g, "")}`}
              >
                {CONSENT_META.phone}
              </a>
            </li>
            <li>
              <span className="text-muted-foreground">Localização:</span>{" "}
              {CONSENT_META.controllerLocation}
            </li>
          </ul>
        </section>

        {/* Footer nav */}
        <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6 text-sm text-muted-foreground">
          <Link to="/consent" className="underline underline-offset-2 hover:text-foreground">
            ← Todos os documentos legais
          </Link>
          <span>
            {CONSENT_META.platform} · {CONSENT_META.canonicalBase}/{doc.slug}
          </span>
        </footer>
      </main>
    </div>
  );
}

export default ConsentDocLayout;
