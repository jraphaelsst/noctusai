/**
 * The married party's NAMED document slots, in display order — the
 * certidão de casamento (migration 103) and the pacto antenupcial
 * (migration 191). Both are rendered by `DocumentoTipoSlot` behind the
 * same `estadoCivilExigeConjuge` gate (`PessoaDocumentosPanel`,
 * `ClienteCardDialog`); one list so a third couple document is one entry,
 * never a third copy of the slot's wiring.
 *
 * `tipo` is the server's `tipo_documento` contract; uploading under it is
 * what makes `identidade_extracao_service` read the file (the pacto's
 * reader writes the couple's `regime_bens` through the conflict-safe path).
 * `artigo` builds the toast copy ("Não foi possível enviar a certidão…").
 */
import { TIPO_CERTIDAO_CASAMENTO } from "./CertidaoCasamentoSlot";

export const TIPO_PACTO_ANTENUPCIAL = "pacto_antenupcial";

export interface SlotDoCasamento {
  tipo: string;
  label: string;
  testId: string;
  artigo: string;
}

export const SLOTS_DO_CASAMENTO: readonly SlotDoCasamento[] = [
  {
    tipo: TIPO_CERTIDAO_CASAMENTO,
    label: "Certidão de casamento",
    testId: "certidao-casamento",
    artigo: "a certidão de casamento",
  },
  {
    tipo: TIPO_PACTO_ANTENUPCIAL,
    label: "Pacto antenupcial",
    testId: "pacto-antenupcial",
    artigo: "o pacto antenupcial",
  },
];
