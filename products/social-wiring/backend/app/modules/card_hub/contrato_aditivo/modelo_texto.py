"""The two aditivo instruments — reviewable TEXT, one line per Word paragraph,
the generator's own conventions (`contrato_gerador.modelo_texto` header):
`{%p … %}` paragraph tags, `V`/`C` agreement, `**…**`/`<u>…</u>` emphasis,
`{{r … }}` for the matrícula quote (built by the generator's own
`contexto._descricao_matricula_rica`).

HOUSE ("ADITIVO AO INSTRUMENTO…", corpus 827/858/868): full re-qualification,
CLÁUSULA PRIMEIRA = the object (cites the original by its signing date and
re-quotes the imóvel), one CLÁUSULA per amendment, then "DAS DEMAIS CLÁUSULAS
E CONDIÇÕES CONTRATUAIS" (ratification) and the signatures.

FORMAL ("PRIMEIRO TERMO ADITIVO", corpus 867): full re-qualification, a
citation sentence naming the original instrument and its date, numbered
sections with "N.k." sub-items, "DA RATIFICAÇÃO" last.

The amending sections' wording lives in `frases.py`; this file only frames
and numbers them.
"""
from __future__ import annotations

#: Shared by both: the closing sentence, the date line and the signature
#: block (same shapes the contract prints — digital vs física, migration 157).
_FECHO = r"""
{%p if digital %}
E, por estarem assim justos e contratados, os contraentes assinam o presente instrumento de forma digital, juntamente com as testemunhas abaixo identificadas.
{%p else %}
E, por estarem assim justos e contratados, os contraentes assinam o presente instrumento em {{ vias }} vias de igual teor e forma, na presença das testemunhas abaixo identificadas.
{%p endif %}
{{ assinatura.local }}, {{ assinatura.data_extenso }}.
{%p if digital %}
**{{ V.NOME }}**
{%p for p in V_signatarios %}
{{ p }}
{%p endfor %}
**{{ C.NOME }}**
{%p for p in C_signatarios %}
{{ p }}
{%p endfor %}
TESTEMUNHAS:
{%p for t in testemunhas %}
{{ t.linha }}
**{{ t.cpf }}**
{%p endfor %}
{%p else %}
**{{ V.NOME }}**
{%p for s in V_assinantes_fisicos %}
{{ linha_assinatura }}
**{{ s.nome }}**
{%p if s.documento %}
**{{ s.documento }}**
{%p endif %}
{%p endfor %}
**{{ C.NOME }}**
{%p for s in C_assinantes_fisicos %}
{{ linha_assinatura }}
**{{ s.nome }}**
{%p if s.documento %}
**{{ s.documento }}**
{%p endif %}
{%p endfor %}
TESTEMUNHAS:
{%p for t in testemunhas_fisicas %}
{{ linha_assinatura }}
**{{ t.nome }}**
{%p if t.documento %}
**{{ t.documento }}**
{%p endif %}
{%p endfor %}
{%p endif %}
"""

#: The one Title line of either template (`documento._estilo_da_linha`).
LINHA_TITULO = "{{ titulo }}"

TEMPLATE_HOUSE = (
    LINHA_TITULO
    + r"""
Pelo presente Aditivo Contratual, e na melhor forma de direito, de um lado, {{ V_qualificacao }}, {{ V.g('denominado','denominada','denominados') }} neste ato simplesmente **"{{ V.NOME }}"**;
E de outro lado, {{ C_qualificacao }}, {{ C.g('denominado','denominada','denominados') }} neste ato simplesmente **"{{ C.NOME }}"**;
<u>CLÁUSULA PRIMEIRA</u> – DO OBJETO DESTE ADITIVO
O presente Aditivo Contratual tem por objetivo alterar as Cláusulas e condições do instrumento original assinado entre as Partes em {{ original.data }} e que trata sobre a negociação do **IMÓVEL:** {{r imovel.descricao_matricula }} Imóvel devidamente cadastrado pela Prefeitura Municipal de {{ imovel.cidade }} sob nº **{{ imovel.inscricao_municipal }}** e caracterizado na Matrícula Nº **{{ imovel.matricula_numero }}** do {{ imovel.cartorio }}.
{%p for s in secoes %}
<u>CLÁUSULA {{ s.ord }}</u> – {{ s.titulo }}
{%p for t in s.paragrafos %}
{{ t }}
{%p endfor %}
{%p endfor %}
<u>CLÁUSULA {{ ord_final }}</u> – DAS DEMAIS CLÁUSULAS E CONDIÇÕES CONTRATUAIS
As demais Cláusulas e condições contratuais, estabelecidas no Contrato original, permanecem válidas e inalteradas, passando o presente Aditivo a integrá-lo para todos os fins de direito.
"""
    + _FECHO
)

TEMPLATE_FORMAL = (
    LINHA_TITULO
    + r"""
Pelo presente instrumento particular, de um lado, {{ V_qualificacao }}, {{ V.g('denominado','denominada','denominados') }} neste ato simplesmente **"{{ V.NOME }}"**;
E de outro lado, {{ C_qualificacao }}, {{ C.g('denominado','denominada','denominados') }} neste ato simplesmente **"{{ C.NOME }}"**;
As partes acima qualificadas resolvem de comum acordo celebrar o presente **{{ ordinal }} TERMO ADITIVO** ao {{ original.titulo }}, firmado em {{ original.data }}, referente ao **IMÓVEL:** {{r imovel.descricao_matricula }} Imóvel devidamente cadastrado pela Prefeitura Municipal de {{ imovel.cidade }} sob nº **{{ imovel.inscricao_municipal }}** e caracterizado na Matrícula Nº **{{ imovel.matricula_numero }}** do {{ imovel.cartorio }}, mediante as cláusulas e condições seguintes:
{%p for s in secoes %}
**{{ s.num }}. {{ s.titulo }}**
{%p for t in s.paragrafos %}
{{ t }}
{%p endfor %}
{%p endfor %}
**{{ n_final }}. DA RATIFICAÇÃO**
Permanecem integralmente válidas, ratificadas e inalteradas todas as demais cláusulas e condições constantes do {{ original.titulo }}, firmado em {{ original.data }}, que não tenham sido expressamente modificadas pelo presente Termo Aditivo.
{{ n_final }}.1. O presente Termo Aditivo passa a integrar o instrumento originário para todos os fins e efeitos de direito, devendo ambos ser interpretados conjuntamente.
"""
    + _FECHO
)

TEMPLATES = {"house": TEMPLATE_HOUSE, "formal": TEMPLATE_FORMAL}


def linhas_do_template(estilo: str) -> list[str]:
    return [linha for linha in TEMPLATES[estilo].splitlines() if linha.strip()]


__all__ = ["LINHA_TITULO", "TEMPLATES", "TEMPLATE_FORMAL", "TEMPLATE_HOUSE", "linhas_do_template"]
