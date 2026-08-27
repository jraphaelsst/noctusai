/**
 * `<DadosPessoaisForm/>` — the fields the document checklist derives from.
 *
 * Presentational (S3): `onSave` is the only callback out.
 *
 * 🔴 WHY THIS EXISTS AT ALL
 * -------------------------
 * Until now the card could SHOW that "Profissão" was outstanding and offered
 * nowhere to fill it in. The backend has accepted these columns on
 * `PATCH /api/clientes/{id}` since migration 068, but no UI ever sent them, so
 * four of the checklist's items were unfillable by any means the operator had
 * — a permanently-red gate, and permanently-red gates stop being read.
 *
 * It is the same failure migration 068's `nome_completo` note describes from
 * the other end, and the reason the checklist and this form are rendered
 * together: the list of what is missing sits directly above the place to
 * supply it.
 *
 * FIELD ORDER IS THE CHECKLIST'S ORDER
 * ------------------------------------
 * Deliberately, and it is not decoration: the sequence is the one an operator
 * actually collects details in, so the form reads top-to-bottom as the
 * conversation goes. RG and CPF are absent because they are satisfied by
 * UPLOADING a document, not by typing — they live in Anexos below.
 *
 * 🔴 GÊNERO'S DEFAULT IS A CONVENIENCE, NOT A VALUE
 * -------------------------------------------------
 * The dropdown shows "Masculino" pre-selected so the common case is one click.
 * Nothing is written until Save, and the checkbox does not tick before then —
 * if an unsaved default counted as data, this item would read green for every
 * existing cliente the day it shipped and could never again answer "who still
 * needs checking".
 */
import { useEffect, useState } from "react";
import { Check, Pencil, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { TooltipIconButton } from "./TooltipIconButton";

/** The taxonomy the UI offers. The COLUMN is unconstrained TEXT on purpose
 *  (migration 068) — a CHECK would freeze a product decision into the schema —
 *  so widening this list needs no migration. */
export const GENEROS = ["Masculino", "Feminino"] as const;

export const GENERO_PADRAO = GENEROS[0];

export interface DadosPessoais {
  nome_completo?: string | null;
  celular?: string | null;
  email?: string | null;
  data_nascimento?: string | null;
  profissao?: string | null;
  genero?: string | null;
}

export interface DadosPessoaisFormProps {
  valores: DadosPessoais;
  onSave: (valores: DadosPessoais) => void;
  saving?: boolean;
  /** Disambiguates the testids when several of these are on screen at once —
   *  one per party on the Documentos tab. */
  testId?: string;
}

function texto(v: string | null | undefined): string {
  return v ?? "";
}

export function DadosPessoaisForm({
  valores,
  onSave,
  saving,
  testId = "dados-pessoais",
}: DadosPessoaisFormProps) {
  const [aberto, setAberto] = useState(false);
  const [draft, setDraft] = useState<DadosPessoais>(valores);

  // Re-seeded when the record changes underneath — an extraction confirming a
  // birthdate writes the column, and a stale draft would silently overwrite it
  // on the next Save.
  useEffect(() => {
    setDraft(valores);
  }, [
    valores.nome_completo,
    valores.celular,
    valores.email,
    valores.data_nascimento,
    valores.profissao,
    valores.genero,
  ]);

  function campo<K extends keyof DadosPessoais>(k: K, v: string) {
    setDraft((d) => ({ ...d, [k]: v === "" ? null : v }));
  }

  function submit() {
    onSave({
      ...draft,
      // The displayed default becomes a real value only here, at Save.
      genero: draft.genero ?? GENERO_PADRAO,
    });
    setAberto(false);
  }

  if (!aberto) {
    return (
      <div className="mb-4">
        {/* Icon-only, caption on hover — and the SAME string on `aria-label`,
            because a hover caption is invisible to a screen reader. */}
        <TooltipIconButton
          label="Editar dados"
          icon={Pencil}
          variant="outline"
          testId={`${testId}-editar-btn`}
          onClick={() => {
            setDraft(valores);
            setAberto(true);
          }}
        />
      </div>
    );
  }

  return (
    <div className="mb-4 space-y-3 rounded-md border p-3" data-testid={testId}>
      <Campo rotulo="Nome Completo" htmlFor={`${testId}-nome`}>
        <Input
          id={`${testId}-nome`}
          value={texto(draft.nome_completo)}
          onChange={(e) => campo("nome_completo", e.target.value)}
          data-testid={`${testId}-nome`}
        />
      </Campo>

      <Campo rotulo="Celular" htmlFor={`${testId}-celular`}>
        <Input
          id={`${testId}-celular`}
          value={texto(draft.celular)}
          onChange={(e) => campo("celular", e.target.value)}
          placeholder="+55 11 99999-8888"
          data-testid={`${testId}-celular`}
        />
      </Campo>

      <Campo rotulo="Email" htmlFor={`${testId}-email`}>
        <Input
          id={`${testId}-email`}
          type="email"
          value={texto(draft.email)}
          onChange={(e) => campo("email", e.target.value)}
          data-testid={`${testId}-email`}
        />
      </Campo>

      <Campo rotulo="Data de Nascimento" htmlFor={`${testId}-nascimento`}>
        <Input
          id={`${testId}-nascimento`}
          type="date"
          value={texto(draft.data_nascimento)}
          onChange={(e) => campo("data_nascimento", e.target.value)}
          data-testid={`${testId}-nascimento`}
        />
      </Campo>

      <Campo rotulo="Profissão" htmlFor={`${testId}-profissao`}>
        <Input
          id={`${testId}-profissao`}
          value={texto(draft.profissao)}
          onChange={(e) => campo("profissao", e.target.value)}
          data-testid={`${testId}-profissao`}
        />
      </Campo>

      <Campo rotulo="Gênero" htmlFor={`${testId}-genero`}>
        <Select
          value={draft.genero ?? GENERO_PADRAO}
          onValueChange={(v) => campo("genero", v)}
        >
          <SelectTrigger id={`${testId}-genero`} data-testid={`${testId}-genero`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GENEROS.map((g) => (
              <SelectItem key={g} value={g}>
                {g}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Campo>

      <div className="flex gap-1">
        <TooltipIconButton
          label={saving ? "Salvando…" : "Salvar dados"}
          icon={Check}
          variant="default"
          disabled={saving}
          onClick={submit}
          testId={`${testId}-salvar`}
        />
        <TooltipIconButton
          label="Cancelar"
          icon={X}
          onClick={() => setAberto(false)}
          testId={`${testId}-cancelar`}
        />
      </div>
    </div>
  );
}

function Campo({
  rotulo,
  htmlFor,
  children,
}: {
  rotulo: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium text-muted-foreground"
      >
        {rotulo}
      </label>
      {children}
    </div>
  );
}
