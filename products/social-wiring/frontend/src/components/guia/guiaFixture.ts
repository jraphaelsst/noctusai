/** Typed fixture of the `GET /api/guia-documentos` contract — shared by the
 *  popover, selector and page tests. */
import type { GuiaDocumentos } from "@/types/guiaDocumentos";

export const GUIA_FIXTURE: GuiaDocumentos = {
  versao: "abc123",
  documentos: [
    {
      tipo_documento: "rg",
      rotulo: "RG",
      campos: [
        { campo: "nome_completo", rotulo: "Nome completo" },
        { campo: "data_nascimento", rotulo: "Data de nascimento" },
        { campo: "rg", rotulo: "RG" },
      ],
      observacao: null,
      usos: ["Qualificação no contrato", "Certidão Receita (data de nascimento)"],
    },
    {
      tipo_documento: "cnh",
      rotulo: "CNH",
      campos: [{ campo: "data_nascimento", rotulo: "Data de nascimento" }],
      observacao: "leitura de todas as páginas",
      usos: ["Qualificação no contrato"],
    },
    {
      tipo_documento: "certidao_casamento",
      rotulo: "Certidão de casamento",
      campos: [],
      observacao: "leitura estruturada do regime de bens",
      usos: [],
    },
  ],
  campos: [
    { campo: "data_nascimento", rotulo: "Data de nascimento", documentos: ["rg", "cnh"] },
    { campo: "nome_completo", rotulo: "Nome completo", documentos: ["rg"] },
    { campo: "regime_bens", rotulo: "Regime de bens", documentos: [] },
  ],
  certidoes: [
    {
      tipo: "cnd_federal",
      linha: "5.1",
      rotulo: "Receita Federal",
      fonte: "infosimples",
      requisitos: [{ documento: "cpf", campos: [{ campo: "data_nascimento", rotulo: "Data de nascimento" }] }],
      credencial: null,
      observacao: null,
    },
    {
      tipo: "debitos_nao_inscritos",
      linha: "5.9",
      rotulo: "Débitos não inscritos",
      fonte: "infosimples",
      requisitos: [{ documento: "cpf", campos: [] }],
      credencial: "govbr",
      observacao: "opcional por padrão",
    },
    {
      tipo: "tjsp",
      linha: "5.4",
      rotulo: "TJSP",
      fonte: "manual",
      requisitos: [],
      credencial: null,
      observacao: "TJSP entrega por e-mail",
    },
  ],
  etapas: [
    {
      chave: "qualificacao",
      rotulo: "Qualificação",
      bloco: "Atendimento",
      exige: [{ rotulo: "Celular", tipo: "campo", ref: "celular" }],
      observacao: null,
    },
    {
      chave: "analise_partes",
      rotulo: "Análise das partes",
      bloco: "Jurídico",
      exige: [
        { rotulo: "RG", tipo: "documento", ref: "rg" },
        { rotulo: "Receita Federal", tipo: "certidao", ref: "cnd_federal" },
      ],
      observacao: "certidões de todos os vendedores",
    },
  ],
  dados_obrigatorios: [
    { chave: "data_nascimento", rotulo: "Data de nascimento", documentos: ["rg", "cnh"], escopo: null, dica: null },
    { chave: "identidade", rotulo: "Documento de identidade", documentos: ["rg", "cnh"], escopo: "pessoa física", dica: "Um documento basta." },
    { chave: "celular", rotulo: "Celular", documentos: [], escopo: null, dica: null },
  ],
};
