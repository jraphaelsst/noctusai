/**
 * `ConsentSettingsPage` — the seed-mounted page at `/settings/ai`.
 *
 * Auto-routed by `createProductApp(...)` for every product (flat AND
 * role-based modes). Hosts the `<AIConsentToggles/>` panel so users can
 * read + toggle every AI feature consent the platform exposes to them.
 *
 * **No per-product code mounts this page.** The seed framework wires
 * the route; products inherit it for free. Products that want to
 * override (e.g. host the toggles inside their own settings shell) can
 * import `AIConsentToggles` directly from `@noctusai/lib/design-system`
 * and add a route to their own `routes` array — but the default-on
 * route always exists.
 */
import { AIConsentToggles } from "@noctusai/lib/design-system";

export function ConsentSettingsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Configurações de IA
        </h1>
        <p className="text-sm text-muted-foreground">
          Gerencie quais recursos de inteligência artificial podem usar seus
          dados. Cada item explica o que a IA faz e que dados ela acessa.
          Você pode alterar suas escolhas a qualquer momento — alterações
          valem a partir do próximo uso (não afetam saídas já geradas).
        </p>
      </header>
      <AIConsentToggles />
    </div>
  );
}

export default ConsentSettingsPage;
