"""Read the holder's profissão off a Brazilian document.

Sibling of `gender.py` / `nacionalidade.py`: pure, label-anchored, returning
`(value, confidence, matched_label)` with confidence as a plain string.

WHERE A PROFISSÃO IS PRINTED
----------------------------
Not on an RG, a CIN or a CNH — none of them carry one. It is printed on:

- a certidão de casamento, per spouse — the older "inteiro teor" model says
  "FULANO, de profissão comerciante, nascido ..." and the form model carries a
  `PROFISSÃO` box under each spouse's qualification;
- a certidão de nascimento's parents' block (the PARENTS' profissão — never the
  holder's, see `_DE_OUTRA_PESSOA`);
- forms (fichas cadastrais, propostas) with a `Profissão:` / `Ocupação:` field.

🔴 LABEL-ANCHORED, NEVER VOCABULARY-DRIVEN
------------------------------------------
There is no closed vocabulary of professions, so an unlabelled word can never
be recognised as one: "comerciante" in a sentence is not evidence of anything.
Only a value sitting right after a `PROFISSÃO` / `OCUPAÇÃO` label is read.

🔴 TWO DIFFERENT LABELLED READINGS -> ABSENCE
---------------------------------------------
A certidão de casamento names two spouses, so a whole-document read finds two
profissões. `find_profissao` reports that as `nenhuma` (same rule as every
sibling: two labelled readings that disagree are a layout this parser cannot
attribute). Per-spouse attribution is `conjuges.find_conjuges`' job — it calls
`find_profissoes` on each spouse's own qualification segment.

WHY THE VALUE IS LOWER-CASED
----------------------------
A qualification prints the profissão in running prose ("brasileiro, casado,
engenheiro civil, ..."), and the contract renderer lower-cases it anyway. The
document's accents are kept — the value is sliced from the ORIGINAL text via
the same offset map `matricula_atos` uses, never re-typed from the normalised
copy.
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets

#: The label, with the "de profissão" prose form, an optional "/OCUPAÇÃO"
#: combo, and any separator before the value — possibly a line break (form
#: layouts print the label in one box and the value in the next line).
_ROTULO_RE = re.compile(
    r"\b(?P<rotulo>(?:DE\s+)?PROFISSAO(?:\s*/\s*OCUPACAO)?|OCUPACAO(?:\s+PRINCIPAL)?)\b"
    r"[ \t]*[:\-–]?[ \t]*\n?[ \t]*"
)

#: Characters a profissão value may contain once normalised.
_VALOR_RE = re.compile(r"[A-Z][A-Z .'/()-]{1,58}")

#: Where a value ends when the document runs on in prose.
_TERMINADORES = re.compile(
    r"\s*(?:[,;\n|]|\.(?:\s|$)|$)"
    r"|\s+(?=(?:NASCID|RESIDENT|DOMICILIAD|PORTADOR|INSCRIT|NATURAL\b|FILH[OA]\b|"
    r"ESTADO\s+CIVIL|NACIONALIDADE|CPF\b|RG\b|CARTEIRA|DATA\b|SEXO\b|NOME\b|"
    r"ENDERECO|RESIDENCIA|E-?MAIL|TELEFONE))"
)

#: A "value" that is really the NEXT label (an empty form box) or a
#: "not stated" marker. Neither is a profissão.
_NAO_VALOR = re.compile(
    r"^(?:NAO\s+(?:CONSTA|DECLARAD[OA]|INFORMAD[OA])|IGNORAD[OA]|SEM\s+PROFISSAO|"
    r"NACIONALIDADE|NATURALIDADE|CPF|RG|ESTADO\s+CIVIL|DATA|NOME|SEXO|ENDERECO|"
    r"FILIACAO|DOCUMENTO|IDENTIDADE|REGIME|MATRICULA|---+|\*+)"
)

#: A profissão label that belongs to SOMEONE ELSE — the parents' block of a
#: certidão de nascimento ("PROFISSÃO DO PAI"). Skipped outright: attributing
#: a parent's profissão to the holder is the error this family exists to
#: avoid.
_DE_OUTRA_PESSOA = re.compile(r"^(?:D[OA]S?\s+(?:PAI|MAE|GENITOR|GENITORA|PAIS|CONJUGE))\b")

#: A "profissão" that is really FILIATION text: a certidão prints
#: "... filho de MARIA APARECIDA e ..." right after the label box, and the
#: value regex happily takes "de maria aparecida e". No profissão starts with
#: "de " and none contains a filiação marker.
_FILIACAO = re.compile(r"^DE\s|\bFILH[OA]S?\s+DE\b|\bFILIACAO\b|\s+E$|\bNETO\s+DE\b")

#: Minimum letters for a value — two-letter noise ("DE") is not a profissão.
_MIN_LETRAS = 3


def _limpar(valor: str) -> str:
    valor = " ".join(valor.split())
    return valor.strip(" .,-–/").lower()


def find_profissoes(text: str) -> list[tuple[str, str, int]]:
    """Every labelled profissão reading, in document order.

    Returns `(valor, rotulo, posicao)` triples — `valor` lower-cased and
    sliced from the ORIGINAL text, `posicao` the reading's offset in the
    original text (so a caller segmenting per person can attribute it).
    """
    if not text:
        return []
    norm, origem = normalized_with_offsets(text)
    out: list[tuple[str, str, int]] = []
    for m in _ROTULO_RE.finditer(norm):
        inicio = m.end()
        resto = norm[inicio:]
        if _DE_OUTRA_PESSOA.match(resto):
            continue
        vm = _VALOR_RE.match(resto)
        if not vm:
            continue
        bruto = vm.group(0)
        corte = _TERMINADORES.search(bruto)
        if corte is not None:
            bruto = bruto[: corte.start()]
        bruto = bruto.rstrip(" .-/")
        if not bruto or _NAO_VALOR.match(bruto) or _FILIACAO.search(bruto):
            continue
        if sum(c.isalpha() for c in bruto) < _MIN_LETRAS:
            continue
        a = inicio
        b = inicio + len(bruto)
        if b > len(origem) or a >= b:
            continue
        literal = text[origem[a] : origem[b - 1] + 1]
        valor = _limpar(literal)
        if valor:
            out.append((valor, " ".join(m.group("rotulo").split()), origem[a]))
    return out


#: 🔴 VOCABULARY GATE (owner rule 2026-10-13). A labelled value must ALSO
#: be a real profissão word: "aposentanda" (a transcription of "aposentada")
#: passed the label anchor and reached a contract. The HEAD word of the value
#: (`engenheiro` in "engenheiro civil") — or the whole value, for fixed
#: multi-word forms ("do lar") — must be in this vocabulary, accent-stripped,
#: masculine and feminine forms both listed. A value outside it is NOT
#: emitted; `avaliar_profissao` reports it as `vocabulario_invalido` with the
#: nearest valid form as a SUGGESTION only (never substituted).
#: Extend with evidence: a legitimate profissão refused here is a one-line
#: addition, a wrong one accepted is a wrong contract.
_HEADS = """
administrador administradora advogado advogada agente agricultor agricultora
agronomo agronoma ajudante almoxarife analista aposentado aposentada arquiteto
arquiteta artesao artesa artista assessor assessora assistente atendente ator
atriz autonomo autonoma auxiliar avicultor aviador bailarino bailarina bancario
bancaria barbeiro barbeira bibliotecario bibliotecaria biologo biologa biomedico
biomedica bombeiro bombeira cabeleireiro cabeleireira caixa caminhoneiro
caminhoneira carpinteiro carteiro carteira chefe cientista cirurgiao cirurgia
comerciante comerciario comerciaria comissario comissaria comprador compradora
confeiteiro confeiteira consultor consultora contador contadora coordenador
coordenadora corretor corretora costureiro costureira cozinheiro cozinheira
delegado delegada dentista desembargador desembargadora desenhista designer
desempregado desempregada diarista diretor diretora domestica domestico
economista economiario economiaria educador educadora eletricista eletrotecnico
empregado empregada empresario empresaria encanador enfermeiro enfermeira
engenheiro engenheira escritor escritora escrivao escriva escriturario
escrituraria estagiario estagiaria estudante estoquista farmaceutico
farmaceutica faxineiro faxineira fazendeiro fazendeira fiscal fisico fisica
fisioterapeuta fonoaudiologo fonoaudiologa fotografo fotografa frentista
funcionario funcionaria garcom garconete gerente geologo geologa gestor gestora
guarda historiador historiadora industrial industriario industriaria
inspetor inspetora instrutor instrutora investidor investidora jardineiro
jardineira jornalista juiz juiza lavrador lavradora lojista marceneiro
mecanico mecanica medico medica mestre metalurgico metalurgica militar
ministro ministra motorista musico musica nutricionista odontologo odontologa
operador operadora operario operaria optometrista ourives padeiro padeira
pecuarista pedagogo pedagoga pedreiro pensionista pesquisador pesquisadora
pescador pescadora piloto pintor pintora policial porteiro porteira produtor
produtora professor professora programador programadora projetista promotor
promotora psicologo psicologa psicanalista psiquiatra publicitario publicitaria
quimico quimica radialista recepcionista representante sacerdote secretario
secretaria seguranca servente servidor servidora socio socia sociologo sociologa
soldado supervisor supervisora tabeliao tabelia tecnico tecnica tecnologo
tecnologa telefonista terapeuta tesoureiro tesoureira topografo topografa
torneiro tradutor tradutora transportador transportadora urbanista vendedor
vendedora veterinario veterinaria vigilante vereador vereadora zelador zeladora
zootecnista oficial capitao coronel sargento tenente major general almirante
comandante delegado perito perita auditor auditora defensor defensora
procurador procuradora analista bancario do engenheira
"""
_VOCABULARIO_HEADS: frozenset[str] = frozenset(_HEADS.split()) - {"do"}
_VOCABULARIO_FRASES: frozenset[str] = frozenset({
    "do lar", "prendas domesticas", "dona de casa", "sem ocupacao",
})

VOCABULARIO_INVALIDO = "vocabulario_invalido"


def avaliar_profissao(valor: Optional[str]) -> tuple[bool, Optional[str]]:
    """`(valida, sugestao)` — is `valor` a profissão in the vocabulary?

    `sugestao` is the nearest vocabulary head (difflib) when invalid — a
    SUGGESTION for a human, never applied to the value.
    """
    import difflib

    from noctusai_lib.integrations.documents.text import strip_accents_upper

    if not valor:
        return (False, None)
    norm = " ".join(strip_accents_upper(valor).lower().split())
    if norm in _VOCABULARIO_FRASES:
        return (True, None)
    cabeca = norm.split()[0] if norm.split() else ""
    if cabeca in _VOCABULARIO_HEADS:
        return (True, None)
    perto = difflib.get_close_matches(cabeca, sorted(_VOCABULARIO_HEADS), n=1, cutoff=0.75)
    return (False, perto[0] if perto else None)


def find_profissao_invalida(text: str) -> Optional[tuple[str, Optional[str]]]:
    """The labelled profissão reading the vocabulary REFUSED, with its
    suggestion — `(valor, sugestao)` — or None. For the extractor's
    `vocabulario_invalido` aviso: the refused value stays visible."""
    for valor, _rotulo, _pos in find_profissoes(text):
        ok, sugestao = avaliar_profissao(valor)
        if not ok:
            return (valor, sugestao)
    return None


def find_profissao(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """The holder's profissão: `(value, confidence, matched_label)`.

    - **alta** — labelled, and every labelled reading agrees.
    - **nenhuma** — nothing labelled, or readings that disagree (a
      two-spouse certidão — see the module docstring).
    """
    leituras = find_profissoes(text)
    if not leituras:
        return (None, "nenhuma", None)
    distintos = {v for v, _, _ in leituras}
    if len(distintos) != 1:
        return (None, "nenhuma", None)
    valor, rotulo, _ = leituras[0]
    if not avaliar_profissao(valor)[0]:
        # Not a profissão word — never emitted as a reading (see
        # `_VOCABULARIO_HEADS`); `find_profissao_invalida` reports it.
        return (None, "nenhuma", None)
    return (valor, "alta", rotulo)


__all__ = [
    "VOCABULARIO_INVALIDO",
    "avaliar_profissao",
    "find_profissao",
    "find_profissao_invalida",
    "find_profissoes",
]
