/**
 * Lais › Conhecimento — section registry (contract section 3). One entry per
 * `secao`: the fields the drawer renders, the defaults used when the section
 * was never saved, and the chip vocabulary (bubble-app-definition section 4).
 */
export type Opcao = { value: string | number | null; label: string };

export interface Campo {
  /** Dot path inside `dados` ("" = the root, used by the phone list). */
  path: string;
  label: string;
  ajuda?: string;
  kind: "radio" | "text" | "textarea" | "switch" | "chips" | "number" | "date" | "readonly";
  opcoes?: Opcao[];
  /** chips: values are numbers (prazos). */
  numeric?: boolean;
  max?: number;
  /** Render only when this holds for the current draft. */
  quando?: (d: Record<string, unknown>) => boolean;
}

export interface SecaoSpec {
  key: string;
  titulo: string;
  descricao: string;
  campos: Campo[];
  /** Custom editor instead of `campos`. */
  custom?: "telefones";
  defaults: unknown;
}

const chips = (...ls: string[]): Opcao[] => ls.map((l) => ({ value: l, label: l }));

export const PESSOAIS = chips(
  "Certidão de estado civil", "Passaporte/RNE", "Carteira de trabalho", "Telefone de contato",
  "Número do PIS", "E-mail", "Extrato do FGTS", "Para PJ: contrato social",
);
export const RENDA = chips(
  "Extrato bancário (3 meses)", "Contra-cheque", "Pró-labore", "Para PJ: balanço patrimonial",
);
export const ENDERECO = chips(
  "Conta de luz", "Conta de água", "Conta de telefone", "Conta de internet",
  "Fatura de cartão de crédito", "Boleto de condomínio",
);
const FIADOR_EXTRA = chips("Para fiador: documento de próprio imóvel quitado", "Matrícula do imóvel");
const CUSTOS = chips(
  "Avaliação do imóvel", "Taxa do registro do imóvel/contrato", "Taxa de engenharia",
  "Emissão de matrícula", "Taxa de análise de crédito",
);
const SEGURADORAS = chips("Porto Seguro", "Tokio Marine", "Fiança Rápida", "Super Save");
const OUTRAS = chips("Loft (antiga CredPago)", "Fianças Bancárias");
const PRAZOS: Opcao[] = [12, 24, 30, 36, 48, 60].map((n) => ({ value: n, label: `${n} meses` }));

const doc = (extra: Opcao[]): Campo[] => [
  { path: "pessoais", label: "Documentos pessoais", kind: "chips", opcoes: [...PESSOAIS, ...extra] },
  { path: "renda", label: "Comprovante de renda", kind: "chips", opcoes: RENDA },
  { path: "endereco", label: "Comprovante de endereço", kind: "chips", opcoes: ENDERECO },
  { path: "adicionais", label: "Detalhes adicionais", kind: "textarea", max: 1000 },
];
const docDefaults = { pessoais: [], renda: [], endereco: [], adicionais: "" };

const aceita = (p: string, label: string): Campo[] => [
  { path: `${p}.aceita`, label: `${label} — aceito?`, kind: "switch" },
  { path: `${p}.oferecer`, label: "A Julia poderá oferecer essa opção", kind: "switch", quando: (d) => !!get(d, `${p}.aceita`) },
];

export const SECOES: Record<string, SecaoSpec> = {
  politicas: {
    key: "politicas", titulo: "Políticas", descricao: "Como funcionam a assinatura de contrato e as visitas.",
    defaults: { assinatura: "digital_fisico", chaves: "acompanhado", chaves_outro: "" },
    campos: [
      { path: "assinatura", label: "Assinatura de contrato", kind: "radio", opcoes: [
        { value: "digital_fisico", label: "Digital e físico" }, { value: "digital", label: "Digital" }, { value: "fisico", label: "Físico" }] },
      { path: "chaves", label: "Chaves para visitar", kind: "radio", opcoes: [
        { value: "acompanhado", label: "Sempre acompanhadas por alguém da equipe" },
        { value: "cliente_busca", label: "Cliente pode buscar a chave e visitar sozinho" },
        { value: "outro", label: "Outro" }] },
      { path: "chaves_outro", label: "Descreva", kind: "text", max: 200, quando: (d) => d.chaves === "outro" },
    ],
  },
  telefones: {
    key: "telefones", titulo: "Telefones da empresa", custom: "telefones", campos: [],
    descricao: "Atualize os contatos dos diferentes setores para que a Julia direcione os clientes corretamente.",
    defaults: [],
  },
  exibir_atendente: {
    key: "exibir_atendente", titulo: "Exibir nome do atendente",
    descricao: "Mensagens enviadas por humanos começam com o nome de quem enviou.",
    defaults: { ativo: false },
    campos: [{ path: "ativo", label: "Exibir nome do atendente nas mensagens", kind: "switch" }],
  },
  recesso: {
    key: "recesso", titulo: "Recesso", descricao: "A Julia avisará que estão em recesso durante o período informado.",
    defaults: { ativo: false, inicio: "", fim: "", mensagem: "" },
    campos: [
      { path: "ativo", label: "Aviso de recesso", kind: "switch" },
      { path: "inicio", label: "Início", kind: "date" },
      { path: "fim", label: "Término", kind: "date" },
      { path: "mensagem", label: "Mensagem", kind: "textarea", max: 500 },
    ],
  },
  venda_info: {
    key: "venda_info", titulo: "Informações da operação", descricao: "Como a Julia atende quem quer comprar.",
    defaults: { atende: true, nomenclatura_corretor: "" },
    campos: [
      { path: "atende", label: "A Julia atende compra?", kind: "switch" },
      { path: "nomenclatura_corretor", label: "Nomenclatura do corretor de venda", kind: "text", max: 40 },
    ],
  },
  venda_documentos: {
    key: "venda_documentos", titulo: "Documentos necessários", descricao: "O que o cliente precisa reunir para comprar.",
    defaults: docDefaults, campos: doc([]),
  },
  venda_financiamento: {
    key: "venda_financiamento", titulo: "Financiamento", descricao: "Como a empresa apoia o financiamento.",
    defaults: { acompanha: false, servicos: [], custos: [], detalhes: "" },
    campos: [
      { path: "acompanha", label: "A empresa acompanha o processo?", kind: "switch" },
      { path: "servicos", label: "Serviços oferecidos", kind: "chips", opcoes: [
        { value: "despachantes", label: "Parceria com despachantes" },
        { value: "simulacao", label: "Oferece simulação de financiamento" },
        { value: "bancos", label: "Parceria com bancos" }] },
      { path: "custos", label: "Custos de financiamento", kind: "chips", opcoes: CUSTOS },
      { path: "detalhes", label: "Detalhes", kind: "textarea", max: 1000 },
    ],
  },
  locacao_info: {
    key: "locacao_info", titulo: "Informações da operação", descricao: "Como a Julia atende quem quer alugar.",
    defaults: { atende: true, nomenclatura_corretor: "" },
    campos: [
      { path: "atende", label: "A Julia atende locação?", kind: "switch" },
      { path: "nomenclatura_corretor", label: "Nomenclatura do corretor de locação", kind: "text", max: 40 },
    ],
  },
  locacao_documentos: {
    key: "locacao_documentos", titulo: "Documentos necessários", descricao: "O que o cliente precisa reunir para alugar.",
    defaults: docDefaults, campos: doc(FIADOR_EXTRA),
  },
  locacao_processo: {
    key: "locacao_processo", titulo: "Processo de locação", descricao: "Prazos, multa e isenção padrão.",
    defaults: { prazo_residencial: [], prazo_comercial: [], multa: "dez_pct", isencao: "nao" },
    campos: [
      { path: "prazo_residencial", label: "Prazo padrão — Residencial", kind: "chips", numeric: true, opcoes: PRAZOS },
      { path: "prazo_comercial", label: "Prazo padrão — Comercial", kind: "chips", numeric: true, opcoes: PRAZOS },
      { path: "multa", label: "Multa rescisória padrão", kind: "radio", opcoes: [
        { value: "dez_pct", label: "10% do valor do contrato proporcional aos meses restantes" },
        { value: "tres_alugueis", label: "3 aluguéis proporcionais ao tempo faltante" }] },
      { path: "isencao", label: "Isenção de multa", kind: "radio", opcoes: [
        { value: "sim", label: "Sim" }, { value: "nao", label: "Não" },
        { value: "mediante_proposta", label: "Mediante proposta e aceitação do proprietário" }] },
    ],
  },
  locacao_garantias: {
    key: "locacao_garantias", titulo: "Garantias", descricao: "Quais garantias a empresa aceita e a Julia pode oferecer.",
    defaults: {
      caucao: { aceita: false, oferecer: false, min_alugueis: null },
      seguro_fianca: { aceita: false, oferecer: false, seguradoras: [] },
      fiador: { aceita: false, oferecer: false, nome_limpo: false, imovel_quitado: false, localizacao: null },
      titulo: { aceita: false, oferecer: false, alugueis: "", inclui_encargos: false },
      outras: { aceita: false, opcoes: [], sem_garantia: false },
    },
    campos: [
      ...aceita("caucao", "Caução"),
      { path: "caucao.min_alugueis", label: "Valor mínimo (nº de aluguéis)", kind: "number", quando: (d) => !!get(d, "caucao.aceita") },
      ...aceita("seguro_fianca", "Seguro fiança"),
      { path: "seguro_fianca.seguradoras", label: "Seguradoras aceitas", kind: "chips", opcoes: SEGURADORAS, quando: (d) => !!get(d, "seguro_fianca.aceita") },
      ...aceita("fiador", "Fiador"),
      { path: "fiador.nome_limpo", label: "Requisito: nome limpo", kind: "switch", quando: (d) => !!get(d, "fiador.aceita") },
      { path: "fiador.imovel_quitado", label: "Requisito: imóvel quitado", kind: "switch", quando: (d) => !!get(d, "fiador.aceita") },
      { path: "fiador.localizacao", label: "Localização", kind: "radio", quando: (d) => !!get(d, "fiador.aceita"), opcoes: [
        { value: null, label: "Qualquer" }, { value: "mesma_cidade", label: "Mesma cidade" }, { value: "mesmo_estado", label: "Mesmo estado" }] },
      ...aceita("titulo", "Título de capitalização"),
      { path: "titulo.alugueis", label: 'Quantidade de aluguéis (ex.: "12", "até 12", "de 6 a 12")', kind: "text", max: 40, quando: (d) => !!get(d, "titulo.aceita") },
      { path: "titulo.inclui_encargos", label: "Inclui encargos (IPTU, condomínio)", kind: "switch", quando: (d) => !!get(d, "titulo.aceita") },
      { path: "outras.aceita", label: "Outras garantias — aceitas?", kind: "switch" },
      { path: "outras.opcoes", label: "Outras garantias aceitas", kind: "chips", opcoes: OUTRAS, quando: (d) => !!get(d, "outras.aceita") },
      { path: "outras.sem_garantia", label: "Possibilidade de alugar sem garantia (requer aprovação do proprietário)", kind: "switch", quando: (d) => !!get(d, "outras.aceita") },
    ],
  },
  perfil_whatsapp: {
    key: "perfil_whatsapp", titulo: "Perfil do WhatsApp",
    descricao: "Como a Julia aparece para o cliente no WhatsApp.",
    defaults: { nome_exibicao: "", descricao: "", sobre: "", endereco: "", email: "", site: "" },
    campos: [
      { path: "nome_exibicao", label: "Nome de exibição", ajuda: "Definido pela persona da Julia.", kind: "readonly" },
      { path: "descricao", label: "Descrição", kind: "textarea", max: 512 },
      { path: "sobre", label: "Sobre", kind: "text", max: 139 },
      { path: "endereco", label: "Endereço", kind: "text" },
      { path: "email", label: "E-mail de contato", kind: "text" },
      { path: "site", label: "Site", kind: "text" },
    ],
  },
  endereco_iptu: {
    key: "endereco_iptu", titulo: "Endereço e IPTU", descricao: "O que a Julia pode informar sobre o imóvel.",
    defaults: { endereco_completo: false, usar_iptu: false },
    campos: [
      { path: "endereco_completo", label: "Envio de endereço completo", ajuda: "Desligado, a Julia informa só bairro e cidade.", kind: "switch" },
      { path: "usar_iptu", label: "Permitir acesso ao IPTU?", ajuda: "Mantenha desligado quando o XML do portal estiver incompleto.", kind: "switch" },
    ],
  },
};

export const ABAS: { key: string; nome: string; secoes: string[] }[] = [
  { key: "geral", nome: "Geral", secoes: ["politicas", "telefones", "exibir_atendente", "recesso"] },
  { key: "vendas", nome: "Vendas", secoes: ["venda_info", "venda_documentos", "venda_financiamento"] },
  { key: "locacao", nome: "Locação", secoes: ["locacao_info", "locacao_documentos", "locacao_processo", "locacao_garantias"] },
  { key: "perfil", nome: "Perfil do WhatsApp", secoes: ["perfil_whatsapp"] },
  { key: "endereco", nome: "Endereço e IPTU", secoes: ["endereco_iptu"] },
];

// ── path helpers over plain JSON ──────────────────────────────────────────
export function get(d: unknown, path: string): unknown {
  if (path === "") return d;
  return path.split(".").reduce<unknown>((a, k) => (a && typeof a === "object" ? (a as Record<string, unknown>)[k] : undefined), d);
}

export function set<T>(d: T, path: string, v: unknown): T {
  if (path === "") return v as T;
  const [k, ...rest] = path.split(".");
  const base = (d && typeof d === "object" ? d : {}) as Record<string, unknown>;
  return { ...base, [k]: rest.length ? set(base[k], rest.join("."), v) : v } as T;
}

export function formatar(c: Campo, v: unknown): string {
  if (c.kind === "switch") return v ? "Sim" : "Não";
  if (c.kind === "chips") return Array.isArray(v) && v.length ? v.map((x) => c.opcoes?.find((o) => o.value === x)?.label ?? String(x)).join(", ") : "—";
  if (c.kind === "radio") return c.opcoes?.find((o) => o.value === (v ?? null))?.label ?? "—";
  return v === null || v === undefined || v === "" ? "—" : String(v);
}
