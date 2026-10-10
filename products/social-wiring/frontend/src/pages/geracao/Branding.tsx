/**
 * Branding (CoreStudio › Configurações, `/media-creation/branding`) — identidade
 * visual por marca. Hosts the existing `BrandingTab` unchanged (esteira-contract
 * §A.5 A-1): brandings grouped by marca, Modelo, Novo branding, Importar design
 * system, tokens / brand book / componentes / ativos / referências.
 *
 * The four states (skeleton / error / empty / data) live in `BrandingTab`
 * (two-signal loading off `useBrandingOverview`).
 */
import { Palette } from "lucide-react";

import { BrandingTab } from "@/components/branding/BrandingTab";

export default function Branding() {
  return (
    <div className="space-y-6 p-6" data-testid="branding-page">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Palette className="h-6 w-6 text-primary" />
          Branding
        </h1>
        <p className="text-sm text-muted-foreground">Identidade visual por marca</p>
      </header>
      <BrandingTab />
    </div>
  );
}
