/**
 * The aditivo editor's local draft — strings while typing, converted to the
 * wire shape (`AditivoPatchBody`) only on save — plus the client-side mirror
 * of the server's 422 rules (`contrato_aditivo/schemas.py`), so the operator
 * finds out from the form, not from a round trip. The SERVER stays the gate;
 * the readiness check (`GET …/geracao`) covers everything beyond shape.
 *
 * Pure functions, no React — unit-tested directly.
 */
import { lerValorDigitado, formatarValorEditavel } from "@/lib/moedaDecimal";
import type {
  AditivoEstilo,
  AditivoOut,
  AditivoPatchBody,
  Alteracao,
  AlteracaoTipo,
  ComissaoMarco,
  ParcelaAditivoIn,
} from "@/hooks/useContratoAditivos";
import type { ModalidadeAssinatura } from "@/hooks/useContratos";

export interface AlteracaoDraft {
  uid: string;
  tipo: AlteracaoTipo;
  clausula: string;
  /** pagamento */
  novoValor: string;
  /** posse / comissão(marco=data) */
  data: string;
  precaria: boolean;
  finalidade: string;
  /** comissão */
  parcelaCorretagem: string;
  marco: ComissaoMarco;
  parcelaNumero: string;
  /** outro */
  titulo: string;
  texto: string;
}

export interface ParcelaDraftRow extends ParcelaAditivoIn {
  uid: string;
}

export interface AditivoDraft {
  estilo: AditivoEstilo;
  assinaturaData: string;
  modalidade: ModalidadeAssinatura;
  alteracoes: AlteracaoDraft[];
  parcelas: ParcelaDraftRow[];
}

let seq = 0;
/** Stable React key for a row that has no server id yet. */
export function novoUid(): string {
  seq += 1;
  return `tmp-${seq}`;
}

export function alteracaoVazia(tipo: AlteracaoTipo): AlteracaoDraft {
  return {
    uid: novoUid(),
    tipo,
    clausula: "",
    novoValor: "",
    data: "",
    precaria: false,
    finalidade: "",
    parcelaCorretagem: "1",
    marco: "parcela",
    parcelaNumero: "",
    titulo: "",
    texto: "",
  };
}

const str = (n: number | null | undefined) => (n == null ? "" : String(n));

function alteracaoParaDraft(a: Alteracao): AlteracaoDraft {
  const d = alteracaoVazia(a.tipo);
  d.clausula = str(a.clausula_alvo ?? null);
  if (a.tipo === "pagamento") d.novoValor = a.novo_valor ? formatarValorEditavel(a.novo_valor) : "";
  if (a.tipo === "posse") {
    d.data = a.data ?? "";
    d.precaria = !!a.precaria;
    d.finalidade = a.finalidade ?? "";
  }
  if (a.tipo === "comissao") {
    d.parcelaCorretagem = str(a.parcela_corretagem);
    d.marco = a.marco;
    d.parcelaNumero = str(a.parcela_numero ?? null);
    d.data = a.data ?? "";
  }
  if (a.tipo === "outro") {
    d.titulo = a.titulo ?? "";
    d.texto = a.texto ?? "";
  }
  return d;
}

export function draftDoAditivo(aditivo: AditivoOut): AditivoDraft {
  return {
    estilo: aditivo.estilo,
    assinaturaData: aditivo.assinatura_data ?? "",
    modalidade: aditivo.modalidade_assinatura,
    alteracoes: aditivo.alteracoes.map(alteracaoParaDraft),
    parcelas: [...aditivo.parcelas]
      .sort((a, b) => a.ordem - b.ordem)
      .map((p) => ({
        uid: p.id,
        tipo: p.tipo,
        valor: p.valor,
        vencimento: p.vencimento,
        evento: p.evento,
        forma_pagamento: p.forma_pagamento,
        favorecido_id: p.favorecido_id,
        confissao_divida: p.confissao_divida,
      })),
  };
}

const inteiro = (v: string): number | null => {
  const t = v.trim();
  if (!/^\d+$/.test(t)) return null;
  return Number(t);
};

function alteracaoParaWire(d: AlteracaoDraft): Alteracao {
  const clausula = inteiro(d.clausula);
  switch (d.tipo) {
    case "pagamento": {
      const novo = lerValorDigitado(d.novoValor).trim();
      return { tipo: "pagamento", clausula_alvo: clausula as number, novo_valor: novo || null };
    }
    case "posse":
      return {
        tipo: "posse",
        clausula_alvo: clausula as number,
        data: d.data,
        precaria: d.precaria,
        finalidade: d.precaria ? d.finalidade.trim() : null,
      };
    case "comissao":
      return {
        tipo: "comissao",
        clausula_alvo: clausula as number,
        parcela_corretagem: inteiro(d.parcelaCorretagem) as number,
        marco: d.marco,
        parcela_numero: d.marco === "parcela" ? inteiro(d.parcelaNumero) : null,
        data: d.marco === "data" ? d.data || null : null,
      };
    case "outro":
      return {
        tipo: "outro",
        clausula_alvo: clausula,
        titulo: d.titulo.trim(),
        texto: d.texto.trim(),
      };
  }
}

/** The content PATCH — `alteracoes`/`parcelas` always sent whole (the
 *  server REPLACES the list); `assinatura_data`/`modalidade` only when they
 *  differ from the stored aditivo. */
export function patchDoDraft(draft: AditivoDraft, aditivo: AditivoOut): AditivoPatchBody {
  const patch: AditivoPatchBody = {
    estilo: draft.estilo,
    alteracoes: draft.alteracoes.map(alteracaoParaWire),
    parcelas: draft.parcelas.map(({ uid: _uid, ...p }) => p),
  };
  if ((draft.assinaturaData || null) !== (aditivo.assinatura_data ?? null)) {
    patch.assinatura_data = draft.assinaturaData || null;
  }
  if (draft.modalidade !== aditivo.modalidade_assinatura) {
    patch.modalidade_assinatura = draft.modalidade;
  }
  return patch;
}

/** `true` when the draft would change something on save. */
export function draftSujo(draft: AditivoDraft, aditivo: AditivoOut): boolean {
  const base = draftDoAditivo(aditivo);
  const semUid = (d: AditivoDraft) =>
    JSON.stringify({
      ...d,
      alteracoes: d.alteracoes.map(({ uid: _u, ...a }) => a),
      parcelas: d.parcelas.map(({ uid: _u, ...p }) => p),
    });
  return semUid(draft) !== semUid(base);
}

/** pt-BR messages per alteração (`uid` → list), mirroring the 422s. Empty
 *  map ⇒ the draft is saveable. */
export function validarDraft(draft: AditivoDraft): Record<string, string[]> {
  const erros: Record<string, string[]> = {};
  const add = (uid: string, msg: string) => {
    (erros[uid] ??= []).push(msg);
  };
  for (const d of draft.alteracoes) {
    const clausula = inteiro(d.clausula);
    const clausulaObrigatoria = d.tipo !== "outro";
    if (d.clausula.trim() === "") {
      if (clausulaObrigatoria) add(d.uid, "Informe o número da cláusula do contrato original.");
    } else if (clausula == null || clausula < 1 || clausula > 59) {
      add(d.uid, "A cláusula é um número inteiro entre 1 e 59.");
    }
    if (d.tipo === "pagamento" && d.novoValor.trim() !== "") {
      const v = Number(lerValorDigitado(d.novoValor));
      if (!Number.isFinite(v) || v <= 0) add(d.uid, "O novo valor deve ser maior que zero.");
    }
    if (d.tipo === "posse") {
      if (!d.data) add(d.uid, "Informe a data da posse.");
      if (d.precaria && !d.finalidade.trim()) add(d.uid, "A posse precária exige a finalidade.");
    }
    if (d.tipo === "comissao") {
      const pc = inteiro(d.parcelaCorretagem);
      if (pc == null || pc < 1 || pc > 12) {
        add(d.uid, "A parcela da corretagem é um número entre 1 e 12.");
      }
      if (d.marco === "parcela") {
        const n = inteiro(d.parcelaNumero);
        if (n == null || n < 1 || n > 99) add(d.uid, "Informe o número da parcela (1 a 99).");
      }
      if (d.marco === "data" && !d.data) add(d.uid, "Informe a data do pagamento da comissão.");
    }
    if (d.tipo === "outro") {
      const t = d.titulo.trim().length;
      if (t < 3 || t > 120) add(d.uid, "O título tem de 3 a 120 caracteres.");
      const x = d.texto.trim().length;
      if (x < 10 || x > 8000) add(d.uid, "O texto tem de 10 a 8000 caracteres.");
    }
  }
  return erros;
}
