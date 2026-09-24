/**
 * Testemunhas — the org's registry of signature witnesses (migration 168).
 *
 * A thin page shell around `<TestemunhasSection/>` — the SAME component the
 * Settings "Imobiliária" tab already renders (`TestemunhasSection.tsx`,
 * `hooks/useTestemunhas.ts`). This page does not re-implement the CRUD; it
 * only gives the registry its own standalone nav destination, same pattern
 * `AgentesFinanceiros.tsx` takes for the financing-bank registry.
 */
import { TestemunhasSection } from "@/components/settings/TestemunhasSection";

export default function Testemunhas() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Testemunhas</h1>
        <p className="text-sm text-muted-foreground">
          Testemunhas cadastradas pela imobiliária — escolhidas por contrato na
          aba Contratos do card.
        </p>
      </div>
      <TestemunhasSection />
    </div>
  );
}
