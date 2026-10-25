/**
 * `<ConjugeDaCertidao/>` — "Lido da certidão de casamento: NOME (nasc. ...) —
 * Adicionar como cônjuge". Presentational: the spouse a certidão READ is
 * offered as a one-click party, so the operator never types a name the
 * document already carries (owner rule: a document-derived field is never
 * hand-typed). The manual "Adicionar cônjuge" stays for when there is no
 * certidão.
 *
 * A 409 "same name + birthdate already in the org" arrives as `candidatos`:
 * the operator links that person or says she is someone new — the refusal is
 * always visible (silent-refusal rule), never swallowed.
 */
import { Button } from "@/components/ui/button";
import type { ConjugeCandidato, ConjugeSugerido } from "@/types/partes";

function dataBr(iso: string | null): string | null {
  if (!iso) return null;
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : null;
}

export interface ConjugeDaCertidaoProps {
  sugestao: ConjugeSugerido;
  onAdicionar: (sugestao: ConjugeSugerido) => void;
  /** Link an existing same-name person (the 409's candidate). */
  onVincular?: (sugestao: ConjugeSugerido, clienteId: string) => void;
  /** "Ela é outra pessoa" — create despite the match. */
  onCriarNovo?: (sugestao: ConjugeSugerido) => void;
  candidatos?: ConjugeCandidato[];
  pending?: boolean;
  /** A visible refusal (server message), or null. */
  erro?: string | null;
}

export function ConjugeDaCertidao({
  sugestao,
  onAdicionar,
  onVincular,
  onCriarNovo,
  candidatos,
  pending,
  erro,
}: ConjugeDaCertidaoProps) {
  const nasc = dataBr(sugestao.data_nascimento);
  return (
    <div
      className="space-y-2 rounded-md border border-border/60 bg-muted/30 p-2 text-sm"
      data-testid="conjuge-da-certidao"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span data-testid="conjuge-da-certidao-texto">
          Lido da certidão de casamento: <strong>{sugestao.nome}</strong>
          {nasc ? ` (nasc. ${nasc})` : ""}
        </span>
        <Button
          size="sm"
          onClick={() => onAdicionar(sugestao)}
          disabled={pending}
          data-testid="conjuge-da-certidao-adicionar"
        >
          Adicionar como cônjuge
        </Button>
      </div>
      {erro && (
        <p className="text-xs text-destructive" role="alert" data-testid="conjuge-da-certidao-erro">
          {erro}
        </p>
      )}
      {candidatos && candidatos.length > 0 && (
        <div className="space-y-1" data-testid="conjuge-da-certidao-candidatos">
          {candidatos.map((c) => (
            <div key={c.cliente_id} className="flex items-center justify-between gap-2">
              <span>
                {c.nome ?? "Sem nome"}
                {dataBr(c.data_nascimento) ? ` (nasc. ${dataBr(c.data_nascimento)})` : ""}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={pending}
                onClick={() => onVincular?.(sugestao, c.cliente_id)}
                data-testid={`conjuge-da-certidao-vincular-${c.cliente_id}`}
              >
                Vincular esta pessoa
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="ghost"
            disabled={pending}
            onClick={() => onCriarNovo?.(sugestao)}
            data-testid="conjuge-da-certidao-criar-novo"
          >
            É outra pessoa — criar nova
          </Button>
        </div>
      )}
    </div>
  );
}
