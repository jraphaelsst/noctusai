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
 * 🔴 GÊNERO HAS NO DEFAULT — A PRE-PICKED DROPDOWN LIES OVER MISSING DATA
 * ------------------------------------------------------------------------
 * It used to show "Masculino" pre-selected as a one-click convenience, with
 * the value only written at Save. That still lied on screen: the checklist
 * (driven by the SAME null column) correctly read the item as missing while
 * this box showed "Masculino" as if answered — and confirming Save with no
 * interaction at all silently WROTE "Masculino" onto a record nobody ever
 * actually stated the gênero of (live-tested, contract-gate audit,
 * 2026-09-22). The box now shows an empty "Selecione" placeholder for a null
 * genero, exactly like Estado civil/Regime de bens below it, and nothing is
 * ever defaulted — only what the operator explicitly picks is sent.
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
import {
  estadoCivilExigeConjuge,
  estadoCivilExigeDataCasamento,
  ehCin,
  rgIgualAoCpf,
} from "@/types/qualificacaoCompletude";

import { TooltipIconButton } from "@noctusai/lib/components";

/** The taxonomy the UI offers. The COLUMN is unconstrained TEXT on purpose
 *  (migration 068) — a CHECK would freeze a product decision into the schema —
 *  so widening this list needs no migration. */
export const GENEROS = ["Masculino", "Feminino"] as const;

export interface DadosPessoais {
  nome_completo?: string | null;
  celular?: string | null;
  email?: string | null;
  data_nascimento?: string | null;
  profissao?: string | null;
  genero?: string | null;

  // ─── Qualificação civil (migration 097) ────────────────────────────────
  //
  // What an "Instrumento Particular de Promessa de Compra e Venda" needs to
  // NAME a party: nome, nacionalidade, estado civil (with regime de bens),
  // profissão, CPF, RG with issuing body, endereço. Of those seven this form
  // used to collect two.
  //
  // `nome_oficial` (migration 071) is the name as printed on an identity
  // document — held BESIDE `nome_completo`, never reconciled with it (see
  // that migration's header). Owner directive, 2026-09-19: now ALSO
  // human-editable, on the same admin-confirmation terms as every field
  // below — see `pendenteConfirmacao` on `DadosPessoaisFormProps`.
  nome_oficial?: string | null;
  cpf?: string | null;
  rg?: string | null;
  /** Issuing body and UF as printed — "SSP/SP". Travels with `rg`: a number
   *  without its issuer is an incomplete qualification. */
  rg_orgao_expedidor?: string | null;
  /** 🔴 Decides whether a spouse must sign. Not a preference field. */
  estado_civil?: string | null;
  regime_bens?: string | null;
  nacionalidade?: string | null;
  /** Migration 117 (contract F6) — the marriage CELEBRATION date. Shown
   *  only while `estado_civil` reads "Casado(a)". */
  data_casamento?: string | null;
  /** Migration 148 — the HUMAN half of contract F6's [Q11] 90-day
   *  freshness check: an emission date for a certidão de estado civil
   *  nobody has uploaded (yet, or ever). Never gated — no extractor ever
   *  writes this column. */
  certidao_estado_civil_emitida_em?: string | null;
  endereco_cep?: string | null;
  endereco_logradouro?: string | null;
  endereco_numero?: string | null;
  endereco_complemento?: string | null;
  endereco_bairro?: string | null;
  endereco_cidade?: string | null;
  endereco_uf?: string | null;
}

/**
 * Every key of `DadosPessoais`, as a runtime value. A `Record` over
 * `keyof DadosPessoais` rather than a hand-kept array, so adding a field to
 * the interface without adding it here is a compile error, not a field that
 * silently never saves.
 */
const CAMPOS_DADOS_PESSOAIS: Record<keyof DadosPessoais, true> = {
  nome_completo: true,
  celular: true,
  email: true,
  data_nascimento: true,
  profissao: true,
  genero: true,
  nome_oficial: true,
  cpf: true,
  rg: true,
  rg_orgao_expedidor: true,
  estado_civil: true,
  regime_bens: true,
  nacionalidade: true,
  data_casamento: true,
  certidao_estado_civil_emitida_em: true,
  endereco_cep: true,
  endereco_logradouro: true,
  endereco_numero: true,
  endereco_complemento: true,
  endereco_bairro: true,
  endereco_cidade: true,
  endereco_uf: true,
};

/**
 * Narrow any object down to the `DadosPessoais` keys it actually carries.
 *
 * 🔴 WHY (found live in prod, 2026-09-24). TypeScript's structural typing lets
 * a WIDER object pass as `DadosPessoais`: `ClienteDetailModal` seeds this form
 * with the full `clientes` row merged under the checklist `valores` (so the
 * qualificação fields prefill), the form's draft starts as that object, and
 * Save sent all ~110 columns. `ClientePatchBody` is a `StrictHttpModel`
 * (`extra="forbid"`), so every save from the card 422'd with "Extra inputs
 * are not permitted" once per non-editable column. Applied at the write
 * (`useDadosPessoaisMutation`), not at one caller, so no seeding path can
 * reintroduce it.
 */
export function apenasDadosPessoais(valores: DadosPessoais): DadosPessoais {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(valores)) {
    if (k in CAMPOS_DADOS_PESSOAIS) out[k] = v;
  }
  return out as DadosPessoais;
}

/**
 * Offered for `estado_civil`. Unconstrained TEXT in the database on purpose
 * (migration 097) — the taxonomy is a product decision, so it lives here
 * beside the dropdown rather than as a CHECK that makes each addition a
 * migration.
 */
export const ESTADOS_CIVIS = [
  "Solteiro(a)",
  "Casado(a)",
  "Divorciado(a)",
  "Viúvo(a)",
  "Separado(a)",
  "União estável",
] as const;

/** Regimes de bens. Only meaningful alongside a married state — the form
 *  shows the field regardless rather than hiding it, because an operator
 *  filling a card top-to-bottom should not have a field appear and disappear
 *  under the cursor. */
export const REGIMES_BENS = [
  "Comunhão parcial de bens",
  "Comunhão universal de bens",
  "Separação total de bens",
  "Separação obrigatória de bens",
  "Participação final nos aquestos",
] as const;

/** Sentinel for "not set" in a Select. Radix treats `value=""` as
 *  uncontrolled, so a real token is needed and is mapped back to null on
 *  save. */
const NAO_INFORMADO = "__nao_informado__";

export interface DadosPessoaisFormProps {
  valores: DadosPessoais;
  onSave: (valores: DadosPessoais) => void;
  saving?: boolean;
  /**
   * The server's own message from the last rejected save (a malformed CPF,
   * e.g.) — the container reads it off its mutation's `error` and hands it
   * back here. RG==CPF is no longer one of these: the server accepts it, and
   * the RG field's own amber notice covers it non-blockingly instead.
   * Rendered in BOTH the open and the collapsed state, because `submit()`
   * closes the editor immediately (optimistic-looking, though the mutation
   * itself is not) and the async rejection lands after that — a caller that
   * only showed it while open would show it to nobody.
   */
  saveError?: string | null;
  /**
   * Item_keys the LAST save deferred to admin confirmation (owner
   * directive, 2026-09-19 — `clientes_service.update_cliente`'s
   * `pendente_confirmacao` in the PATCH response). A field named here was
   * NOT written: the document's value keeps prevailing until an admin
   * decides via the conflicts queue. Rendered as a clear notice under the
   * field so the operator does not read the still-old value as a rejected
   * save. Cleared by the caller on the next successful non-deferred save
   * (this form does not track it across renders itself — it is
   * presentational, S3).
   */
  pendenteConfirmacao?: string[];
  /** A CIN file is on this person's record — RG == CPF is then its valid
   *  state and the amber RG==CPF notice is never shown (see `ehCin`). */
  temCin?: boolean;
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
  saveError,
  pendenteConfirmacao,
  temCin = false,
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
    // 097's fields re-seed on the same terms: an extraction that confirms a
    // CPF writes the column, and a stale draft would overwrite it on Save.
    valores.nome_oficial,
    valores.cpf,
    valores.rg,
    valores.rg_orgao_expedidor,
    valores.estado_civil,
    valores.regime_bens,
    valores.nacionalidade,
    valores.data_casamento,
    valores.certidao_estado_civil_emitida_em,
    valores.endereco_cep,
    valores.endereco_logradouro,
    valores.endereco_numero,
    valores.endereco_complemento,
    valores.endereco_bairro,
    valores.endereco_cidade,
    valores.endereco_uf,
  ]);

  const pendente = (campo: string) => pendenteConfirmacao?.includes(campo) ?? false;

  function campo<K extends keyof DadosPessoais>(k: K, v: string) {
    setDraft((d) => ({ ...d, [k]: v === "" ? null : v }));
  }

  function submit() {
    // No field here is ever defaulted — `draft` carries exactly what the
    // operator typed or picked. A null `genero` (never touched) is sent as
    // null, same as any other untouched field.
    onSave(draft);
    setAberto(false);
  }

  if (!aberto) {
    return (
      <div className="mb-4 space-y-1">
        {saveError && (
          <p className="text-xs text-destructive" data-testid={`${testId}-erro`}>
            {saveError}
          </p>
        )}
        {/* Visible in the COLLAPSED state too, deliberately — this is the
            state most of the time on screen, and an edit that never landed
            (see PendenteAviso below) must not read as a rejected save just
            because the editor closed. */}
        {!!pendenteConfirmacao?.length && (
          <p
            className="rounded border border-amber-400/50 bg-amber-50 p-2 text-xs text-amber-800"
            data-testid={`${testId}-pendente-resumo`}
          >
            Aguardando confirmação de um administrador: {pendenteConfirmacao.join(", ")}.
            O valor do documento continua valendo até a decisão.
          </p>
        )}
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

  // Never for a CIN — there RG == CPF is correct by design (2026-09-23).
  const rgIgualCpf =
    rgIgualAoCpf(draft.rg, draft.cpf) && !ehCin(draft.rg_orgao_expedidor, temCin);

  return (
    <div className="mb-4 space-y-3 rounded-md border p-3" data-testid={testId}>
      {saveError && (
        <p
          className="rounded border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive"
          data-testid={`${testId}-erro`}
        >
          {saveError}
        </p>
      )}
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
        <PendenteAviso ativo={pendente("data_nascimento")} testId={`${testId}-nascimento`} />
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
          value={draft.genero ?? NAO_INFORMADO}
          onValueChange={(v) =>
            campo("genero", v === NAO_INFORMADO ? "" : v)
          }
        >
          <SelectTrigger id={`${testId}-genero`} data-testid={`${testId}-genero`}>
            <SelectValue placeholder="Selecione" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NAO_INFORMADO}>Selecione</SelectItem>
            {GENEROS.map((g) => (
              <SelectItem key={g} value={g}>
                {g}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <PendenteAviso ativo={pendente("genero")} testId={`${testId}-genero`} />
      </Campo>

      {/* ─── Qualificação civil (migration 097) ────────────────────────────
          The block a contract needs and a CRM never did. Grouped and labelled
          as such so it reads as one job — "qualify this person" — rather than
          seven more boxes appended to the contact details above. */}
      <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Qualificação
      </p>

      {/* Migration 071, human-editable since the owner's 2026-09-19
          directive. Labelled distinctly from "Nome Completo" above — the two
          are compared, never reconciled (see that migration's header). */}
      <Campo rotulo="Nome completo (como no documento)" htmlFor={`${testId}-nome-oficial`}>
        <Input
          id={`${testId}-nome-oficial`}
          value={texto(draft.nome_oficial)}
          onChange={(e) => campo("nome_oficial", e.target.value)}
          data-testid={`${testId}-nome-oficial`}
        />
        <PendenteAviso ativo={pendente("nome_oficial")} testId={`${testId}-nome-oficial`} />
      </Campo>

      <Campo rotulo="CPF" htmlFor={`${testId}-cpf`}>
        <Input
          id={`${testId}-cpf`}
          value={texto(draft.cpf)}
          onChange={(e) => campo("cpf", e.target.value)}
          placeholder="412.954.238-98"
          data-testid={`${testId}-cpf`}
        />
        <PendenteAviso ativo={pendente("cpf")} testId={`${testId}-cpf`} />
      </Campo>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="RG" htmlFor={`${testId}-rg`}>
          <Input
            id={`${testId}-rg`}
            value={texto(draft.rg)}
            onChange={(e) => campo("rg", e.target.value)}
            placeholder="52.179.965-X"
            data-testid={`${testId}-rg`}
          />
          {/* Informational, never blocking — the Carteira de Identidade
              Nacional (CIN) legitimately prints the CPF number as the RG, so
              this coincidence is a normal, correct state for a growing share
              of documents, not an error. The server no longer refuses the
              write for it either; this is just a nudge to double-check the
              document when the two numbers happen to match. */}
          {rgIgualCpf && (
            <p
              className="mt-1 rounded border border-amber-400/50 bg-amber-50 p-1.5 text-xs text-amber-800"
              data-testid={`${testId}-rg-igual-cpf`}
            >
              RG igual ao CPF — correto apenas para a Carteira de Identidade
              Nacional (CIN). Confira o documento.
            </p>
          )}
          <PendenteAviso ativo={pendente("rg")} testId={`${testId}-rg`} />
        </Campo>
        {/* Side by side with the number because the two are one fact: an RG
            without its issuer does not identify a document. */}
        <Campo rotulo="Órgão expedidor" htmlFor={`${testId}-rg-orgao`}>
          <Input
            id={`${testId}-rg-orgao`}
            value={texto(draft.rg_orgao_expedidor)}
            onChange={(e) => campo("rg_orgao_expedidor", e.target.value)}
            placeholder="SSP/SP"
            data-testid={`${testId}-rg-orgao`}
          />
        </Campo>
      </div>

      <Campo rotulo="Nacionalidade" htmlFor={`${testId}-nacionalidade`}>
        <Input
          id={`${testId}-nacionalidade`}
          value={texto(draft.nacionalidade)}
          onChange={(e) => campo("nacionalidade", e.target.value)}
          placeholder="brasileiro(a)"
          data-testid={`${testId}-nacionalidade`}
        />
        <PendenteAviso ativo={pendente("nacionalidade")} testId={`${testId}-nacionalidade`} />
      </Campo>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="Estado civil" htmlFor={`${testId}-estado-civil`}>
          <Select
            value={draft.estado_civil ?? NAO_INFORMADO}
            onValueChange={(v) =>
              campo("estado_civil", v === NAO_INFORMADO ? "" : v)
            }
          >
            <SelectTrigger
              id={`${testId}-estado-civil`}
              data-testid={`${testId}-estado-civil`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NAO_INFORMADO}>Não informado</SelectItem>
              {ESTADOS_CIVIS.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <PendenteAviso ativo={pendente("estado_civil")} testId={`${testId}-estado-civil`} />
        </Campo>
        {/* 🔴 CONDITIONED ON MARRIAGE (owner directive, this slice). Used to
            render unconditionally on the argument that a field appearing and
            disappearing moves the form under the cursor of someone filling
            it top-to-bottom — but a regime de bens is meaningless for a
            single person, and asking every operator to skip a field that
            never applies to most cards is worse than the field moving once,
            the one time `estado_civil` is set. `estadoCivilExigeConjuge`
            (CC art. 1.647) is the SAME predicate the cônjuge panel, the
            certidão slot and the checklist suggestions below gate on — one
            rule, not four. */}
        {estadoCivilExigeConjuge(draft.estado_civil) && (
          <Campo rotulo="Regime de bens" htmlFor={`${testId}-regime-bens`}>
            <Select
              value={draft.regime_bens ?? NAO_INFORMADO}
              onValueChange={(v) =>
                campo("regime_bens", v === NAO_INFORMADO ? "" : v)
              }
            >
              <SelectTrigger
                id={`${testId}-regime-bens`}
                data-testid={`${testId}-regime-bens`}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NAO_INFORMADO}>Não informado</SelectItem>
                {REGIMES_BENS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <PendenteAviso ativo={pendente("regime_bens")} testId={`${testId}-regime-bens`} />
          </Campo>
        )}
      </div>

      {/* Migration 117 (contract F6) — shown only for a LEGALLY married party
          (`uniao_estavel` has no "casamento" to date — see
          `estadoCivilExigeDataCasamento`'s docblock). Not gated the way
          estado_civil/regime_bens above are visually flagged twice: it is
          its OWN CAMPOS entry, so it gets its OWN notice. */}
      {estadoCivilExigeDataCasamento(draft.estado_civil) && (
        <Campo rotulo="Data de casamento" htmlFor={`${testId}-data-casamento`}>
          <Input
            id={`${testId}-data-casamento`}
            type="date"
            value={texto(draft.data_casamento)}
            onChange={(e) => campo("data_casamento", e.target.value)}
            data-testid={`${testId}-data-casamento`}
          />
          <PendenteAviso ativo={pendente("data_casamento")} testId={`${testId}-data-casamento`} />
        </Campo>
      )}

      {/* Migration 148 — the manual half of contract F6's [Q11] 90-day
          freshness check. Always shown (unlike data_casamento above):
          required for a VENDEDOR regardless of estado civil, and this form
          has no notion of "which side this person is on" to hide it for a
          comprador. Never gated — no extractor ever writes this column. */}
      <Campo
        rotulo="Certidão de estado civil — data de emissão (obrigatório para vendedores)"
        htmlFor={`${testId}-certidao-estado-civil-emitida-em`}
      >
        <Input
          id={`${testId}-certidao-estado-civil-emitida-em`}
          type="date"
          value={texto(draft.certidao_estado_civil_emitida_em)}
          onChange={(e) => campo("certidao_estado_civil_emitida_em", e.target.value)}
          data-testid={`${testId}-certidao-estado-civil-emitida-em`}
        />
      </Campo>

      <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Endereço
      </p>

      <div className="grid grid-cols-3 gap-2">
        <Campo rotulo="CEP" htmlFor={`${testId}-cep`}>
          <Input
            id={`${testId}-cep`}
            value={texto(draft.endereco_cep)}
            onChange={(e) => campo("endereco_cep", e.target.value)}
            placeholder="05407-002"
            data-testid={`${testId}-cep`}
          />
        </Campo>
        <div className="col-span-2">
          <Campo rotulo="Logradouro" htmlFor={`${testId}-logradouro`}>
            <Input
              id={`${testId}-logradouro`}
              value={texto(draft.endereco_logradouro)}
              onChange={(e) => campo("endereco_logradouro", e.target.value)}
              data-testid={`${testId}-logradouro`}
            />
          </Campo>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="Número" htmlFor={`${testId}-numero`}>
          <Input
            id={`${testId}-numero`}
            value={texto(draft.endereco_numero)}
            onChange={(e) => campo("endereco_numero", e.target.value)}
            data-testid={`${testId}-numero`}
          />
        </Campo>
        <Campo rotulo="Complemento" htmlFor={`${testId}-complemento`}>
          <Input
            id={`${testId}-complemento`}
            value={texto(draft.endereco_complemento)}
            onChange={(e) => campo("endereco_complemento", e.target.value)}
            data-testid={`${testId}-complemento`}
          />
        </Campo>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Campo rotulo="Bairro" htmlFor={`${testId}-bairro`}>
          <Input
            id={`${testId}-bairro`}
            value={texto(draft.endereco_bairro)}
            onChange={(e) => campo("endereco_bairro", e.target.value)}
            data-testid={`${testId}-bairro`}
          />
        </Campo>
        <Campo rotulo="Cidade" htmlFor={`${testId}-cidade`}>
          <Input
            id={`${testId}-cidade`}
            value={texto(draft.endereco_cidade)}
            onChange={(e) => campo("endereco_cidade", e.target.value)}
            data-testid={`${testId}-cidade`}
          />
        </Campo>
        <Campo rotulo="UF" htmlFor={`${testId}-uf`}>
          <Input
            id={`${testId}-uf`}
            value={texto(draft.endereco_uf)}
            onChange={(e) => campo("endereco_uf", e.target.value.toUpperCase())}
            maxLength={2}
            placeholder="SP"
            data-testid={`${testId}-uf`}
          />
        </Campo>
      </div>

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

/**
 * "Aguardando confirmação do administrador" — the visible half of the
 * owner's provenance directive (2026-09-19). A field this shows for is one
 * the last Save DID send, but the server held back: the value on screen is
 * still whatever the OPEN box shows (the operator's own typed draft, not
 * what actually landed), so this is placed right under the box it applies
 * to, never merely in the summary banner above — the exact field must be
 * unambiguous.
 */
function PendenteAviso({ ativo, testId }: { ativo: boolean; testId: string }) {
  if (!ativo) return null;
  return (
    <p className="mt-1 text-xs text-amber-700" data-testid={`${testId}-pendente`}>
      Aguardando confirmação de um administrador — o valor do documento
      continua valendo até a decisão.
    </p>
  );
}
