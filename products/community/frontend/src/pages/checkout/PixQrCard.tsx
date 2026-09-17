/**
 * PixQrCard — inline Pix QR display for `/assinar` (community-m2-contract.md
 * §Frontend: "for Pix, show the QR (payload + image) inline instead of
 * redirecting"). Co-located with `Assinar.tsx`, the only consumer.
 */
import { useState } from "react";
import { Copy, CheckCircle2 } from "lucide-react";
import { Button } from "@noctusai/lib/design-system";
import { Card } from "@/components/FormControls";
import type { PixQr } from "@/hooks/useCheckout";

export function PixQrCard({ pixQr }: { pixQr: PixQr }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(pixQr.payload);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied by the browser — the payload text is
      // still visible/selectable below, so nothing is actually lost.
    }
  }

  return (
    <Card data-testid="pix-qr-card">
      <p className="text-sm font-medium text-foreground">Pague com Pix para ativar sua assinatura</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Escaneie o QR code abaixo no app do seu banco, ou copie o código Pix.
      </p>
      <div className="mt-4 flex justify-center">
        <img
          src={`data:image/png;base64,${pixQr.imagem_base64}`}
          alt="QR code Pix"
          className="h-48 w-48 rounded-md border border-border"
        />
      </div>
      <div className="mt-4 space-y-2">
        <p className="break-all rounded-md border border-border bg-muted/50 p-2 text-xs text-muted-foreground">
          {pixQr.payload}
        </p>
        <Button type="button" variant="outline" className="w-full" onClick={() => void handleCopy()}>
          {copied ? (
            <>
              <CheckCircle2 className="h-4 w-4" /> Copiado!
            </>
          ) : (
            <>
              <Copy className="h-4 w-4" /> Copiar código Pix
            </>
          )}
        </Button>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Expira em {new Date(pixQr.expira_em).toLocaleString("pt-BR")}. Assim que o pagamento for
        confirmado, sua assinatura é ativada automaticamente.
      </p>
    </Card>
  );
}
