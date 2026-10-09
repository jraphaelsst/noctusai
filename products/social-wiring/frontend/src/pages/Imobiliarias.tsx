/**
 * Imobiliárias — the org's registry of signing companies. A thin page shell
 * around `<ImobiliariasSection/>` (same pattern as `pages/Testemunhas.tsx`):
 * the CRUD lives in the component, never duplicated here.
 */
import { ImobiliariasSection } from "@/components/settings/ImobiliariasSection";

export default function Imobiliarias() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Imobiliárias</h1>
        <p className="text-sm text-muted-foreground">
          Imobiliárias que assinam os contratos — escolhida por contrato na aba
          Contratos do card.
        </p>
      </div>
      <ImobiliariasSection />
    </div>
  );
}
