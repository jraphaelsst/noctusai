/**
 * A `rascunho` is invisible to orgs and to the AI until an admin publishes it (contract DC3, §6.2).
 * The 422 `rascunho_incompleto` answer carries `faltando`; it is rendered here as a list, never as a toast alone.
 */
import { Button } from "@/components/ui/button";
import { ROTULO_FALTANDO } from "./rotulos";

interface Props {
  /** What is missing — the server's `faltando`, or the client-side mirror of the rule. */
  faltando: string[];
  alteracoesNaoSalvas: boolean;
  pending: boolean;
  onPublicar: () => void;
}

export function PublicarBar({ faltando, alteracoesNaoSalvas, pending, onPublicar }: Props) {
  return (
    <div
      role="region"
      aria-label="Publicação"
      data-testid="publicar-bar"
      className="flex flex-col gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          <strong>Rascunho.</strong> Só administradores veem esta estrutura. Publique para que as organizações e a IA
          passem a usá-la.
        </p>
        <Button onClick={onPublicar} disabled={pending || alteracoesNaoSalvas}>
          {pending ? "Publicando..." : "Publicar"}
        </Button>
      </div>
      {alteracoesNaoSalvas && (
        <p className="text-xs text-muted-foreground">Salve ou descarte as alterações antes de publicar.</p>
      )}
      {faltando.length > 0 && (
        <div role="alert" className="text-destructive">
          <p>Para publicar, informe:</p>
          <ul className="list-disc pl-5">
            {faltando.map((f) => (
              <li key={f}>{ROTULO_FALTANDO[f] ?? f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
