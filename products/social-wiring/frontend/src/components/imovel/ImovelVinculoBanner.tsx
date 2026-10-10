/** "Vinculado" banner (CONTRACT §8.7) + admin-only "Desvincular". */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useDesvincularImovel } from "@/hooks/useImovelDuplicatas";

export default function ImovelVinculoBanner({
  vinculo,
}: {
  vinculo: { manual_codigo: string; vista_codigo: string };
}) {
  const isAdmin = useIsOrgAdmin();
  const desvincular = useDesvincularImovel();
  const [confirmando, setConfirmando] = useState(false);

  async function confirmar() {
    setConfirmando(false);
    try {
      const res = await desvincular.mutateAsync(vinculo.manual_codigo);
      if (res?.legal?.status === "erro") {
        toast.warning(
          res.legal.mensagem ?? "Desvinculado, mas os dados legais não puderam ser atualizados.",
        );
      } else {
        toast.success("Imóveis desvinculados.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Não foi possível desvincular.");
    }
  }

  const link = (c: string) => (
    <Link to={`/imoveis/${encodeURIComponent(c)}`} className="font-medium underline">
      {c}
    </Link>
  );

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100"
      data-testid="imovel-vinculo-banner"
    >
      <p>
        <strong>Vinculado.</strong> Cadastro manual {link(vinculo.manual_codigo)} vinculado ao
        anúncio {link(vinculo.vista_codigo)}.
      </p>
      {isAdmin && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={desvincular.isPending}
          onClick={() => setConfirmando(true)}
          data-testid="imovel-desvincular"
        >
          Desvincular
        </Button>
      )}
      <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desvincular imóveis?</AlertDialogTitle>
            <AlertDialogDescription>
              O cadastro manual deixa de herdar os dados do anúncio e o par volta a ser sugerido
              como possível duplicado. Nada é perdido.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmar} data-testid="imovel-desvincular-confirmar">
              Desvincular
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
