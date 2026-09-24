"""The clause wording — reviewable TEXT, one line per Word paragraph (spec §2).

`documento.template_bytes()` turns every non-blank line below into one
paragraph of a python-docx document and caches the bytes; no binary .docx is
committed. docxtpl syntax: `{%p ... %}` on its own line is a paragraph-level
tag (the paragraph holding it is dropped).

Conventions (spec §2.0):
- `cl.<key>.ORD` / `cl.<key>.ref` — computed numbers; an excluded clause is
  absent, so referencing it fails the render.
- `par('<key>')` — "Parágrafo Primeiro:" … / "Parágrafo Único:".
- `V` / `C` — agreement for vendedores / compradores; no article is spelled.
- `brl(x)` — digits and por-extenso from one Decimal; `dias(n)` likewise.
- `{{r ... }}` — a docxtpl RICH-TEXT slot: the value MUST be built by
  `contexto._descricao_matricula_rica` (via the seed `docx_render`
  adapter's `rich_text()`), never a plain string — a plain string in a
  `{{r ... }}` slot renders as EMPTY. Used exactly once, for the matrícula
  literal quote's bold/underline (contract §5).
- Long, data-dependent phrases (qualificação, each parcela line, certidão
  items, pendências) are composed in `frases.py` — also plain wording, kept
  next to the rules that choose between variants.
- 🔴 [pronome-lhe-lhes-lado-errado] `"comprar-{{ C.pl('lhe','lhes') }}"` (DO
  PREÇO) is the one dative clitic in this template that agrees with `C`
  (comprador), not `V` — verified against reference contract 08 (RESIDENCIAL
  EUROVILLE): "A VENDEDORA [ONE seller] compromete-se a vender para os
  COMPRADORES e, estes a comprar-**lhes** o referido imóvel" — plural
  despite a SINGLE seller, so the clitic tracks who is doing the buying
  (`C`), never the seller side a naive reading of "buy FROM him" suggests.

Divergences from the sample contracts are the spec's merged forms (§2.3–2.17
"Divergence" notes). Wording whose data is MISSING (§6.1: parcela splits,
posse prorrogação/compensação, permuta delivery obligations, the permuta
imóvel's own ônus) is not present at all — the gate reports the gap.
"""
from __future__ import annotations

TEMPLATE = r"""
INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA DE BEM IMÓVEL – {{ imovel.titulo_curto|upper }} – {{ imovel.cidade|upper }} - {{ imovel.uf|upper }}.
Pelo presente Instrumento Particular de Promessa de Venda e Compra de Bem Imóvel, e na melhor forma de direito, de um lado, {{ V_qualificacao }}, {{ V.g('denominado','denominada','denominados') }} neste ato simplesmente "{{ V.NOME }}";
E de outro lado, {{ C_qualificacao }}, {{ C.g('denominado','denominada','denominados') }} neste ato simplesmente "{{ C.NOME }}";
Com fundamento na autonomia privada, por vontade livre dos contratantes, que se comprometem a observar os princípios de lealdade, boa-fé e transparência que norteiam o presente contrato, desde sua celebração até após a sua execução, têm entre si justo e contratado o disposto nas cláusulas seguintes do presente Contrato de Promessa de Venda e Compra de Bem Imóvel, que pactuam firmemente, a saber:

CLÁUSULA {{ cl.objeto.ORD }} – DO OBJETO DO CONTRATO
{{ V.ART }} {{ V.NOME }}, {{ titulo_aquisitivo }}, {{ V.pl('tornou-se','tornaram-se') }} {{ V.g('legítimo proprietário','legítima proprietária','legítimos proprietários') }} do imóvel descrito a seguir:
IMÓVEL: {{r imovel.descricao_matricula }} Imóvel devidamente cadastrado pela Prefeitura Municipal de {{ imovel.cidade }} sob nº {{ imovel.inscricao_municipal }} e caracterizado na Matrícula Nº {{ imovel.matricula_numero }} do {{ imovel.cartorio }}.
{%p if tem_itens_integrantes %}
{{ par('objeto') }} As partes estabelecem de comum acordo, que fará parte integrante da presente transação os itens relacionados a seguir: {{ itens_integrantes }}
{%p endif %}

CLÁUSULA {{ cl.preco.ORD }} – DO PREÇO E CONDIÇÕES DE PAGAMENTO
{{ V.ART }} {{ V.NOME }} {{ V.pl('compromete-se','comprometem-se') }} a vender para {{ C.art }} {{ C.NOME }} e, {{ C.estes }} a comprar-{{ C.pl('lhe','lhes') }} o referido imóvel{% if ad_corpus %} na situação ad corpus (no estado em que se encontra){% endif %}, descrito na {{ cl.objeto.ref }}, pelo preço certo, firme e irreajustável de {{ brl(preco) }}, que deverá ser pago em moeda corrente nacional conforme a seguir estipulado:
{%p for p in parcelas %}
Parcela {{ p.num }}:{{ p.texto }}
{%p endfor %}
{%p if tem_financiamento %}
{{ par('preco') }} {{ C.ART }} {{ C.NOME }}, {{ C.pl('declara','declaram') }} estar {{ C.g('ciente','ciente','cientes') }} das regras de financiamento bancário, sendo de sua inteira e total responsabilidade a obtenção de crédito imobiliário, para a quitação da parcela {{ p_ref.financiamento }} deste presente instrumento.
{%p endif %}
{%p if tem_permuta and tem_financiamento %}
{{ par('preco') }} As Partes estabelecem que a Escritura Pública de Permuta do imóvel melhor descrito na Parcela {{ p_ref.permuta }} acima, deverá ocorrer de maneira concomitante, a assinatura do Contrato de Financiamento bancário, previsto para quitação da parcela {{ p_ref.financiamento }}.
{%p endif %}

{%p if tem_confissao %}
CLÁUSULA {{ cl.confissao.ORD }} – DA CONFISSÃO DE DÍVIDA, VENCIMENTO ANTECIPADO, FORÇA EXECUTIVA E GARANTIA DA OBRIGAÇÃO.
{{ C.ART }} {{ C.NOME }}, de forma livre, consciente, expressa, irrevogável e irretratável, {{ C.pl('reconhece, confessa e declara','reconhecem, confessam e declaram') }} dever {{ V.aos }} {{ V.NOME }} o saldo remanescente do preço da compra e venda objeto deste instrumento, correspondente às parcelas previstas na {{ cl.preco.ref }}, especialmente aquelas descritas como Parcelas {{ confissao.parcelas_nums }}, totalizando o valor nominal de {{ brl(confissao.total) }}, acrescido dos juros remuneratórios convencionados de {{ pct_extenso(confissao.juros_am) }} ao mês, observados os respectivos vencimentos contratualmente estabelecidos.
{{ par('confissao') }} A presente confissão de dívida é realizada nos termos dos artigos 389, 394, 395 e seguintes do Código Civil, constituindo obrigação líquida, certa e exigível, ficando expressamente reconhecido {{ C.pelos }} {{ C.NOME }} que o presente instrumento particular, desde que assinado pelos devedores e por duas testemunhas, possui natureza de título executivo extrajudicial, nos termos do artigo 784, inciso III, do Código de Processo Civil, podendo ser promovida a execução judicial independentemente de prévia ação de conhecimento.
{{ par('confissao') }} O inadimplemento de qualquer parcela sujeitará {{ C.art }} {{ C.NOME }}, automaticamente e independentemente de qualquer aviso, interpelação ou notificação judicial ou extrajudicial, ao pagamento dos seguintes encargos:
I – multa moratória de 2% (dois por cento) sobre o valor da parcela em atraso;
II – juros moratórios de 1% (um por cento) ao mês, calculados pro rata die;
III – correção monetária pelo IGPM, ou por outro índice oficial que venha a substituí-lo, desde o vencimento até o efetivo pagamento;
IV – reembolso integral das despesas comprovadamente suportadas {{ V.pelos }} {{ V.NOME }} para cobrança do débito, inclusive custas, emolumentos e honorários advocatícios, judiciais ou extrajudiciais.
{{ par('confissao') }} O atraso superior a 30 (trinta) dias no pagamento de qualquer parcela, ou o inadimplemento de 02 (duas) parcelas, consecutivas ou alternadas, importará, de pleno direito e independentemente de qualquer notificação, no vencimento antecipado de todas as parcelas vincendas, tornando imediatamente exigível o saldo devedor integral, acrescido dos encargos previstos neste contrato.
{{ par('confissao') }} {{ V.ART }} {{ V.NOME }} {{ V.pl('poderá','poderão') }} promover a execução judicial da obrigação pelo saldo integral antecipadamente vencido ou apenas pelas parcelas vencidas, a seu exclusivo critério, sem que isso importe em renúncia ao direito de exigir posteriormente as demais prestações ou configure novação da dívida.
{{ par('confissao') }} A eventual tolerância {{ V.dos }} {{ V.NOME }} quanto ao atraso no pagamento, recebimento parcial de valores, renegociação verbal, concessão de prazo adicional ou qualquer outra liberalidade não importará novação, remissão, transação, renúncia de direitos ou alteração das condições pactuadas, permanecendo íntegros todos os direitos decorrentes deste contrato.
{{ par('confissao') }} A obrigação ora confessada possui caráter autônomo quanto à sua exigibilidade, permanecendo plenamente válida e eficaz ainda que haja a lavratura da escritura pública, a imissão na posse, o registro da transmissão da propriedade ou qualquer outro ato decorrente da execução deste contrato, extinguindo-se somente mediante quitação expressa e escrita concedida {{ V.pelos }} {{ V.NOME }}.
{{ par('confissao') }} Para fins de eventual execução judicial, fica facultado {{ V.aos }} {{ V.NOME }} apresentar simples demonstrativo atualizado do débito, contendo a discriminação das parcelas vencidas, dos encargos incidentes e dos pagamentos eventualmente realizados, o qual será considerado suficiente para apuração do saldo devedor, ressalvado {{ C.aos }} {{ C.NOME }} o direito de impugnação na forma da legislação processual.
{{ par('confissao') }} O pagamento antecipado de qualquer parcela poderá ser realizado {{ C.pelos }} {{ C.NOME }}, hipótese em que incidirão apenas os juros remuneratórios calculados pro rata die, até a data da efetiva liquidação da respectiva obrigação, observadas as regras deste contrato.
{%p if C.plural %}
{{ par('confissao') }} A presente confissão de dívida constitui obrigação solidária entre os COMPRADORES, que respondem integralmente pelo cumprimento das obrigações assumidas, facultando {{ V.aos }} {{ V.NOME }} exigir de qualquer deles o pagamento da totalidade da dívida, sem prejuízo do direito de regresso entre os devedores.
{%p endif %}
{{ par('confissao') }} Permanecem vinculadas à presente confissão de dívida todas as demais obrigações previstas neste contrato, inclusive as cláusulas de mora, inadimplemento, rescisão e perdas e danos, que deverão ser interpretadas de forma complementar e não excludente.
{%p if confissao.garantia_texto %}
{{ par('confissao') }} {{ C.ART }} {{ C.NOME }}, {{ C.pl('apresenta','apresentam') }} neste ato, a título de garantia para pagamento dos valores ora confessados como devedores, {{ confissao.garantia_texto }}.
{%p endif %}
{%p endif %}

CLÁUSULA {{ cl.certidoes.ORD }} – DAS CERTIDÕES E DOCUMENTOS
{{ certidoes.apresentantes_texto }} {{ certidoes.apresenta }} neste momento as certidões em {{ certidoes.seus_nomes }}, abaixo relacionadas:
{%p for g in certidoes.grupos %}
{{ g.num }} - Em nome de {{ g.em_nome_de|upper }}{% if g.sufixo %} - {{ g.sufixo }}{% endif %}
{%p for i in g.itens %}
{{ g.num }}.{{ loop.index }} – {{ i }}{{ '.' if loop.last else ';' }}
{%p endfor %}
{%p endfor %}
{%p for g in certidoes.grupos_imovel %}
{{ g.num }} – Em Relação ao Imóvel – {{ g.titulo }}
{%p for i in g.itens %}
{{ g.num }}.{{ loop.index }} – {{ i }}{{ '.' if loop.last else ';' }}
{%p endfor %}
{%p endfor %}
{%p if tem_permuta %}
{{ par('certidoes') }} Caso as certidões acima mencionadas, apresentem fatos positivos para {{ V.art }} {{ V.NOME }} ou para {{ C.art }} {{ C.NOME }}, deverão ser apresentados os devidos esclarecimentos, provando que tais apontamentos não colocam em risco a presente transação, no prazo máximo de {{ prazo_esclarecimentos }} dias a contar da presente assinatura.
{{ par('certidoes') }} As "Partes" se comprometem ainda a apresentar as certidões e documentos abaixo relacionados, e as eventualmente "PENDENTES" no prazo máximo de {{ prazo_pendencias }} dias a contar da assinatura do presente, sendo certo que as contas de consumo, IPTU e condomínio deverão ser quitadas por ambas as partes dos dois imóveis referenciados neste contrato, até a entrega de cada chave à respectiva parte, de acordo com a {{ cl.posse.ref|lower }} que trata da posse sobre os imóveis:
{%p else %}
{{ par('certidoes') }} {{ V.ART }} {{ V.NOME }} {{ V.pl('se compromete','se comprometem') }} ainda a apresentar as certidões eventualmente PENDENTES, assim como as abaixo relacionadas e devidos esclarecimentos para qualquer apontamento verificado nas certidões, no prazo de {{ dias(prazo_pendencias) }}, a contar da assinatura do presente instrumento:
{%p endif %}
{%p for d in certidoes.pendencias %}
{{ d.letra }}-) {{ d.texto }}{{ '.' if loop.last else ';' }}
{%p endfor %}

CLÁUSULA {{ cl.onus.ORD }} – DO ÔNUS SOBRE {{ 'OS IMÓVEIS' if tem_permuta else 'O IMÓVEL' }}
{%p if tem_permuta %}
{{ V.ART }} {{ V.NOME }} e {{ C.art }} {{ C.NOME }} declaram expressamente, sob as penas da lei, inclusive responsabilidade civil e criminal, que não existem ações reais ou pessoais reipersecutórias que recaiam sobre os imóveis objeto desta transação, respondendo, ambos, pela evicção de direito, na forma da legislação vigente.
{%p else %}
{{ V.ART }} {{ V.NOME }} {{ V.pl('declara','declaram') }} expressamente sob responsabilidade civil e criminal, que não existem ações reais ou pessoais reipersecutórias que envolvam o imóvel objeto desta transação, respondendo pela evicção de direito.
{%p endif %}
{%p if tem_saldo_devedor %}
{{ V.ART }} {{ V.NOME }} {{ V.pl('declara','declaram') }} ainda existir saldo de financiamento do imóvel, junto a {{ onus.credor }}, conforme descrito {{ onus.fonte_texto }} da Matrícula do imóvel, {{ onus.quitacao_texto }}.
{%p endif %}
{%p if tem_saldo_devedor and onus.quitacao == 'compradores_prazo' %}
{{ par('onus') }} {{ C.ART }} {{ C.NOME }} {{ C.pl('se compromete','se comprometem') }} a fazer a quitação do saldo devedor e apresentar a matrícula com o registro da baixa da alienação fiduciária, no prazo de até {{ dias(onus.prazo_dias) }} da assinatura do presente instrumento.
{%p endif %}

CLÁUSULA {{ cl.posse.ORD }} – DA POSSE SOBRE {{ 'OS IMÓVEIS' if tem_permuta else 'O IMÓVEL' }}
{%p if tem_permuta %}
{{ C.ART }} {{ C.NOME }}, {{ C.pl('assume','assumem') }} a obrigação de fazer a entrega da posse do imóvel situado à {{ permuta.endereco_curto }} {{ V.aos }} {{ V.NOME }}, no prazo máximo de {{ dias(permuta.posse_prazo) }} a contar {{ permuta.posse_marco_texto }}.
Durante o referido período, {{ C.art }} {{ C.NOME }} {{ C.pl('se compromete','se comprometem') }} a permitir o acesso ao imóvel, mediante prévio agendamento, a qualquer tempo, {{ V.aos }} {{ V.NOME }}, ao novo proprietário ou a terceiros por estes autorizados, para fins de vistoria, medição, planejamento ou quaisquer outras providências relacionadas ao imóvel.
{{ V.ART }} {{ V.NOME }}, por sua vez, {{ V.pl('assume','assumem') }} a obrigação de entregar {{ C.aos }} {{ C.NOME }} a posse do imóvel situado à {{ imovel.endereco_curto }}, no prazo máximo de {{ dias(posse.prazo) }}, a contar {{ posse.marco_texto }}.
{{ par('posse') }} As Partes se comprometem a entregar seus imóveis, de maneira limpa e organizada, livre e desimpedida de coisas e pessoas estranhas a esta negociação.
{%p if tem_multa_diaria_posse %}
{{ par('posse') }} Fica convencionada multa de {{ brl(posse.multa_diaria) }} por dia de atraso na hipótese de que {{ V.art }} {{ V.NOME }}, {{ V.pl('apresente','apresentem') }} obstáculos para acesso ao imóvel situado à {{ imovel.endereco_curto }} ou entrega das chaves, no prazo ora pactuado, sem prejuízo de eventual propositura de demanda de imissão na posse ou ação de perdas e danos.
{{ par('posse') }} Fica convencionada a mesma multa de {{ brl(posse.multa_diaria) }} por dia de atraso na hipótese de que {{ C.art }} {{ C.NOME }}, {{ C.pl('apresente','apresentem') }} obstáculos para acesso ao imóvel situado à {{ permuta.endereco_curto }} ou entrega das chaves, no prazo ora pactuado, sem prejuízo de eventual propositura de demanda de imissão na posse ou ação de perdas e danos.
{%p endif %}
{%p else %}
{{ V.ART }} {{ V.NOME }} {{ V.pl('outorgará','outorgarão') }} a posse do imóvel objeto deste contrato {{ C.aos }} {{ C.NOME }}, em até {{ dias(posse.prazo) }} a contar {{ posse.marco_texto }}{{ posse.condicao_frase }}.
{%p if tem_multa_diaria_posse %}
{{ par('posse') }} Fica convencionada multa de {{ brl(posse.multa_diaria) }} por dia de atraso na hipótese de que {{ V.art }} {{ V.NOME }}, {{ V.pl('apresente','apresentem') }} obstáculos para acesso ao imóvel ou entrega das chaves, no prazo ora pactuado, sem prejuízo de eventual propositura de demanda de imissão na posse ou ação de perdas e danos.
{%p endif %}
{%p endif %}

CLÁUSULA {{ cl.tributos.ORD }} - DO PAGAMENTO DOS TRIBUTOS, TAXAS E CONTRIBUIÇÕES
{%p if tem_permuta %}
{{ V.ART }} {{ V.NOME }} e {{ C.art }} {{ C.NOME }}, cada qual se responsabilizará pelos pagamentos pontuais dos tributos, taxas e contribuições de melhoria, incidentes sobre seu imóvel, que se vencerem a partir da data da transmissão da posse sobre o imóvel adquirido, especialmente o IPTU, Condomínio, Luz, água e gás.
{{ par('tributos') }} {{ V.ART }} {{ V.NOME }} e {{ C.art }} {{ C.NOME }} se obrigam a informar a aquisição do imóvel objeto deste contrato, no cadastro da Prefeitura Municipal, cadastro de administradora de Condomínios, bem como junto às concessionárias públicas, a fim de que para o próximo exercício de contribuição os respectivos avisos de cobrança sejam lançados em seu nome no prazo máximo de 30 dias após a posse e se obrigam a dar ciência {{ V.aos }} {{ V.NOME }} e {{ C.aos }} {{ C.NOME }} das transferências feitas, apresentando os devidos protocolos ou a devida titularidade trocada.
{{ par('tributos') }} As despesas decorrentes da transmissão de cada imóvel, tais como emolumentos de cartório, registro e ITBI, serão suportadas pela parte que o recebe.
{%p else %}
{{ C.ART }} {{ C.NOME }} se {{ C.pl('responsabilizará','responsabilizarão') }} pelos pagamentos pontuais dos tributos, taxas e contribuições de melhoria, que se vencerem a partir do recebimento da posse do imóvel, ficando {{ V.art }} {{ V.NOME }} {{ V.g('responsável','responsável','responsáveis') }} pelos pagamentos das contas de consumo como: água, luz e gás (se aplicável), tributos como IPTU e despesa condominial que tenham seu fato gerador antes da entrega da posse do imóvel.
{{ par('tributos') }} {{ C.ART }} {{ C.NOME }} se {{ C.pl('obriga','obrigam') }} a informar a aquisição do imóvel objeto deste contrato, no cadastro da Prefeitura Municipal, cadastro de administradora de Condomínios, bem como junto às concessionárias públicas, a fim de que para o próximo exercício de contribuição os respectivos avisos de cobrança sejam lançados em seu nome no prazo máximo de 30 dias após a posse e se {{ C.pl('obriga','obrigam') }} a dar ciência {{ V.aos }} {{ V.NOME }} das transferências feitas, apresentando os protocolos ou a devida titularidade trocada.
{{ par('tributos') }} As despesas decorrentes deste instrumento, tais como, emolumentos de cartório, registro, ITBI, serão suportadas {{ C.pelos }} {{ C.NOME }}.
{%p endif %}

CLÁUSULA {{ cl.irretratabilidade.ORD }} – DA IRRETRATABILIDADE, VINCULAÇÃO E RESCISÃO
O presente Instrumento Particular de Promessa de Compra e Venda de Bem Imóvel, é firmado em caráter irrevogável e irretratável, não se admitindo arrependimento por nenhum dos contratantes, vinculando não só as partes, mas também seus herdeiros e/ou sucessores, que deverão fazer da presente venda sempre boa, firme e valiosa, tendo como base legal os artigos 417 a 420 do Código Civil, nos termos dos parágrafos seguintes.
{{ par('irretratabilidade') }} Não obstante a irretratabilidade e irrevogabilidade do presente Instrumento, considerar-se-á rescindido o presente Instrumento, por descumprimento das obrigações assumidas {{ V.pelos }} {{ V.NOME }} ou {{ C.pelos }} {{ C.NOME }}{{ rescisao.cura_frase }}.
{{ par('irretratabilidade') }} Fica ajustado entre as Partes, multa rescisória no valor de {{ brl(multa_rescisoria) }}, a ser paga pela parte que der causa à rescisão, que arcará ainda com todos os custos comprovadamente gerados durante o processo de compra e venda até a data da rescisão.
{{ par('irretratabilidade') }} Caso a rescisão do Contrato seja motivada {{ V.pelos }} {{ V.NOME }}, {{ V.estes }} {{ V.pl('deverá','deverão') }}, além do pagamento da multa rescisória, devolver {{ C.aos }} {{ C.NOME }}, todas as importâncias efetivamente recebidas {{ C.g('deste','desta','destes') }}, no prazo máximo de 2 dias úteis após a rescisão do Contrato.
{{ par('irretratabilidade') }} Caso a rescisão do Contrato seja motivada {{ C.pelos }} {{ C.NOME }}, caracterizada pela falta de pagamento de qualquer das parcelas, {{ C.estes }} {{ C.pl('perderá','perderão') }} o valor pago na Parcela {{ p_ref.sinal }} (Sinal) em favor {{ V.dos }} {{ V.NOME }}, a título indenizatório.

CLÁUSULA {{ cl.mora.ORD }} – DA MORA E DO INADIMPLEMENTO
Na hipótese de atraso no pagamento de qualquer das parcelas do preço, {{ C.art }} {{ C.NOME }} {{ C.pl('arcará','arcarão') }} com multa moratória de 2% (dois por cento) sobre o valor do débito, acrescido de juros moratórios de 1% (um por cento) ao mês e correção monetária pelo IGPM.

{%p if tem_declaracao_partes %}
CLÁUSULA {{ cl.declaracao_partes.ORD }} – DECLARAÇÃO DAS PARTES
Declaram {{ V.art }} {{ V.NOME }} e {{ C.art }} {{ C.NOME }} expressamente e sob as penas da lei, não estarem vinculados a nenhuma das restrições previdenciárias previstas na Lei 8.212/91, bem como, não existirem feitos ajuizados, fundados em ação real ou pessoais reipersecutórias, impostos e taxas em atraso ou outro qualquer ônus que recaia sobre {{ 'os imóveis objetos' if tem_permuta else 'o imóvel objeto' }} do presente instrumento, e tudo nos termos do Decreto 93.240, de 09 de setembro de 1986, que regulamentou a Lei Federal nº 7.433 de 18 de dezembro de 1985.
{%p endif %}

CLÁUSULA {{ cl.vistoria.ORD }} – DA VISTORIA PRÉVIA
{%p if tem_permuta %}
Declaram {{ V.art }} {{ V.NOME }} e {{ C.art }} {{ C.NOME }} haverem vistoriado tanto a área interna quanto a externa dos imóveis objetos da presente negociação, bem como as áreas de uso comum do condomínio onde os mesmos estão localizados, estando cientes do estado atual de conservação de ambas as áreas ora mencionadas.
{%p else %}
{{ C.pl('Declara','Declaram') }} {{ C.art }} {{ C.NOME }} {{ C.pl('haver','haverem') }} pessoalmente vistoriado o imóvel objeto da presente negociação{% if imovel.em_condominio %}, bem como as áreas de uso comum do condomínio onde o mesmo está localizado{% endif %}, estando {{ C.g('ciente','ciente','cientes') }} do estado atual de conservação {{ 'de ambas as áreas ora mencionadas' if imovel.em_condominio else 'do imóvel' }}, pelo que {{ C.pl('manifesta','manifestam') }} seu conhecimento e aceitação.
{%p endif %}

{%p if tem_assinatura_digital %}
CLÁUSULA {{ cl.assinatura_digital.ORD }} - DA ASSINATURA DIGITAL
As Partes expressamente concordam em utilizar e reconhecem como válida qualquer forma de comprovação de anuência aos termos ora acordados em formato eletrônico através da plataforma {{ assinatura.plataforma_nome }} ({{ assinatura.plataforma_url }}). A formalização do negócio por meio digital será suficiente para a validade e integral vinculação das partes ao presente Contrato, nos termos da Medida Provisória n.º 2.200-2/2001 e demais normas aplicáveis, produzindo os mesmos efeitos legais das assinaturas manuscritas.
{%p endif %}

CLÁUSULA {{ cl.registro.ORD }} – AUTORIZAÇÃO DE REGISTRO DESTE INSTRUMENTO
Fica o Senhor Oficial do Registro de Imóveis competente autorizado, mediante provocação de qualquer das partes contratantes, a promover o registro do presente instrumento, na forma hábil.

CLÁUSULA {{ cl.resolutiva.ORD }} – CLÁUSULA RESOLUTIVA EXPRESSA
A presente transação é realizada em caráter irrevogável e irretratável, exceto no caso de inadimplência das partes, quando a rescisão do presente contrato se operará de pleno direito, nos termos do art. 474 do Código Civil, com as penalidades previstas na {{ cl.irretratabilidade.ref }} deste.{% if resolutiva_notificacao_email %} Declara-se expressamente ciência acerca da eventual inadimplência se caracteriza pela omissão ao pagamento do preço nos termos e condições previstos na {{ cl.preco.ref|lower }}, cuja notificação para constituição da mora resolutiva se dará por notificação encaminhada ao endereço eletrônico informado pelas partes.{% endif %}

{%p if tem_intermediacao %}
CLÁUSULA {{ cl.intermediacao.ORD }} - DA INTERMEDIAÇÃO
Neste ato {{ corretagem.contratantes_texto }} {{ corretagem.contrata }} {{ corretagem.empresas_texto }}, para promover a presente intermediação:
{%p for q in corretagem.qualificados %}
{{ q }}
{%p endfor %}
{{ par('intermediacao') }} {{ corretagem.contratantes_texto_cap }} e {{ corretagem.contratadas_texto }} ajustam de comum acordo, o valor de corretagem em {{ brl(corretagem.total) }} e deverá ser pago {{ corretagem.parcelamento_texto }}, por ocasião do recebimento {{ corretagem.marcos_texto }} da {{ cl.preco.ref }} deste Contrato, da seguinte forma:
{%p for s in corretagem.splits %}
{{ s }}{{ '.' if loop.last else ';' }}
{%p endfor %}
{{ par('intermediacao') }} Fica ajustado que em caso de rescisão do presente Contrato, a PARTE que der causa a rescisão, fica com o encargo do pagamento do valor de {{ corretagem.pct_rescisao }} de corretagem.
{%p endif %}

CLÁUSULA {{ cl.foro.ORD }} - DA ELEIÇÃO DO FORO
As partes elegem o foro da Comarca de {{ foro.comarca }}, para dirimir as questões decorrentes do presente instrumento, renunciando a outro, por mais privilegiado que seja.
{%p if tem_assinatura_digital %}
E, por estarem assim justos e contratados, os contraentes assinam o presente instrumento de forma digital, na presença das testemunhas abaixo identificadas.
{%p else %}
E, por estarem assim justos e contratados, os contraentes assinam o presente instrumento em {{ vias }} vias de igual teor e forma, na presença das testemunhas abaixo identificadas.
{%p endif %}
{{ assinatura.local }}, {{ assinatura.data_extenso }}.
{%p if tem_assinatura_digital %}
{{ V.NOME }}
{%p for p in V_signatarios %}
{{ p }}
{%p endfor %}
{{ C.NOME }}
{%p for p in C_signatarios %}
{{ p }}
{%p endfor %}
TESTEMUNHAS:
{%p for t in testemunhas %}
{{ t.linha }}
{{ t.cpf }}
{%p endfor %}
{%p else %}
{{ V.NOME }}
{%p for s in V_assinantes_fisicos %}
{{ linha_assinatura }}
{{ s.nome }}
{%p if s.documento %}
{{ s.documento }}
{%p endif %}
{%p endfor %}
{{ C.NOME }}
{%p for s in C_assinantes_fisicos %}
{{ linha_assinatura }}
{{ s.nome }}
{%p if s.documento %}
{{ s.documento }}
{%p endif %}
{%p endfor %}
TESTEMUNHAS:
{%p for t in testemunhas_fisicas %}
{{ linha_assinatura }}
{{ t.nome }}
{%p if t.documento %}
{{ t.documento }}
{%p endif %}
{%p endfor %}
{%p endif %}
"""


def linhas_do_template() -> list[str]:
    """Every non-blank template line — one Word paragraph each."""
    return [linha for linha in TEMPLATE.splitlines() if linha.strip()]


__all__ = ["TEMPLATE", "linhas_do_template"]
