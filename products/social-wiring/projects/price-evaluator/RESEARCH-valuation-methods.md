# Pesquisa — métodos de avaliação de imóveis (avaliador de preço, One Consultoria / Granja Viana)

> Pesquisa web de 2026-10-14 (sessão de entrevista do avaliador de preço do SW).
> Legenda: **[S]** = vindo da fonte citada · **[Syn]** = síntese/recomendação · **[NV]** = não verificado a partir de fonte primária ou reproduzida.
> Ressalva principal: o texto da ABNT NBR 14653 é pago e não público. As tabelas abaixo vêm de (a) laudos que as reproduzem literalmente e (b) artigos técnicos do IBAPE. **Comprar a NBR 14653-1:2019 e a 14653-2:2011 antes de tratar qualquer limiar como vinculante.**
>
> Companheiros: [`RESEARCH-valorization-drivers.md`](RESEARCH-valorization-drivers.md) · [`DECISIONS.md`](DECISIONS.md) · roadmap `project-history/roadmaps/sw-price-evaluator-2026-10.md`.

---

## 1. ABNT NBR 14653 (Parte 1:2019, Parte 2:2011)

**Edições vigentes [S]:** Parte 1 de 2001, revista em 2019. Parte 2 (imóveis urbanos) de 2004, revista em 2011. Parte 3 (rurais) revista em 2019. Uma votação ISO de revisão das Partes 1, 2, 3 e 5 correu de 28/08/2023 a 01/10/2023. Temas listados para a futura revisão da Parte 2 incluem "uso de dados da internet", "avaliações algorítmicas (BACEN)" e "uso de IA em avaliações". Fonte: [Antão, IBAPE 2023](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/SERGIO-ANTAO-Avaliacao-de-bens-25-anos.pdf).
- [Syn] Se a Parte 2 for revista, as regras para um AVM como o nosso mudam. Acompanhar.

**Métodos [S]:**
- **Comparativo direto de dados de mercado.** A NBR 14653-1:2019 manda preferi-lo "sempre que possível" quando o objetivo é valor de mercado. Fonte: [Guerra/IBAPE, slides citando a 14653-1:2019](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/ARTHUR-GUERRA-Escolha-de-Variaveis-na-avaliacao-de-imoveis.pdf).
- **Evolutivo** (terreno + benfeitorias): VI = (VT + CB) · FC. VT = valor do terreno, CB = custo de reedição das benfeitorias, FC = fator de comercialização. Em 2011 substituiu o antigo método "residual". Fonte: [Antão](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/SERGIO-ANTAO-Avaliacao-de-bens-25-anos.pdf).
- Outros métodos da norma: involutivo, capitalização da renda, custo de reedição.

**Duas escalas de rigor separadas [S]:**
- *Grau de fundamentação* (profundidade do trabalho) vale para todos os métodos.
- *Grau de precisão* vale só para o método comparativo. Medido pela amplitude do intervalo de confiança de 80% em torno da estimativa central.
- A edição 2011 separou precisão do *campo de arbítrio*: faixa de ±15% que o avaliador pode usar para variáveis que o modelo não captura (era ±10% para fatores em 2004). Fontes: [Antão](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/SERGIO-ANTAO-Avaliacao-de-bens-25-anos.pdf); citação da 14653-1:2019 em [Guerra](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/ARTHUR-GUERRA-Escolha-de-Variaveis-na-avaliacao-de-imoveis.pdf).

**Tratamento por fatores, 14653-2:2011 Tabela 4 [S].** Reproduzida literalmente num [laudo CPCON](https://static.suporteleiloes.com.br/lutheroleiloescombr/bens/10946/arquivos/sl-bem-10946-6a95cbec98c7e-6a95cbecb1da6.pdf).

| Item | Grau III | Grau II | Grau I |
|---|---|---|---|
| 1 Caracterização do imóvel avaliando | completa quanto a todas as variáveis | completa quanto aos fatores usados | situação paradigma |
| 2 Coleta de dados | verificados pelo autor do laudo | verificados por profissional credenciado pelo autor | dados de terceiros admitidos |
| 3 Mínimo de dados efetivamente usados | **12** | **6** | **3** |
| 4 Identificação dos dados | todas as características, com fotos | todas as características | só as ligadas aos fatores usados |
| 5 Extrapolação | não admitida | admitida para uma variável | admitida |
| 6 Intervalo admissível de ajuste, por fator e para o conjunto | **0,90–1,10** | **0,80–1,20** | **0,50–1,50** |

- Pontuação: Grau III = 3 pontos por item, II = 2, I = 1. Mínimos totais: III = 15 pontos, II = 9, I = 6.
- Itens 3, 5 e 6 são obrigatórios no grau pretendido.
- Grau III exige laudo na "modalidade completa".
- Conflito: uma fonte secundária cita a norma IBAPE-SP 2011 como 3 / 5 / 12 dados ([Jurídico Certo](https://juridicocerto.com/p/silvio-nunes-pereira/artigos/tres-cinco-ou-vinte-e-quatro-a-quantidade-de-comparativos-que-um-laudo-de-avaliacao-precisa-ter-8137)). A tabela ABNT reproduzida diz 3 / 6 / 12. Conferir na norma comprada.

**Modelos de regressão, 14653-2:2011 Tabela 1 [S].** Reproduzida numa [dissertação de mestrado UPV na biblioteca do IBAPE](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2022/06/Tesina-de-M%C3%A1ster_versi%C3%B3n-final_Igor-AF.pdf).
- n mínimo **6(k+1)** para Grau III, **4(k+1)** para II, **3(k+1)** para I, k = nº de variáveis independentes.
- Significância máxima bicaudal de cada regressor: **10% / 20% / 30%**.
- Significância máxima do teste F do modelo: **1% / 2% / 5%**.
- Extrapolação: não admitida no III. No II, admitida para uma variável só, com limites. No I, admitida dentro de limites; o texto reproduzido inclui "não superiores a 100% do limite amostral".
- Regras 2011 para variáveis qualitativas/dicotômicas:
  - n ≤ 30: pelo menos 3 observações de cada característica (ni ≥ 3).
  - 30 < n ≤ 100: ni ≥ 10% de n.
  - n > 100: ni ≥ 10.
  - Fonte: [Antão](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/SERGIO-ANTAO-Avaliacao-de-bens-25-anos.pdf).
- A 14653-1:2019 admite **um** fator de homogeneização prévio a uma regressão, p.ex. o fator fonte que converte preço de oferta em condição de transação. Fonte: [Guerra](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/ARTHUR-GUERRA-Escolha-de-Variaveis-na-avaliacao-de-imoveis.pdf).

**Grau de precisão, Tabela 5 [S, com conflito].**
- A Tabela 5 tem um título só, cobrindo regressão e fatores ([dissertação](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2022/06/Tesina-de-M%C3%A1ster_versi%C3%B3n-final_Igor-AF.pdf)).
- O laudo CPCON a reproduz como amplitude ≤30% = III, 30–50% = II, >50% = I.
- A versão mais citada é III ≤30%, II ≤40%, I ≤50%. Essa versão é [NV]: não foi possível obter a imagem da tabela.
- Amplitude = (limite superior − limite inferior) / valor central, a 80% de confiança.

**Formato de laudo [S]:** as edições 2011 e 2019 aboliram o "parecer técnico" como categoria não classificada de avaliação ([Antão](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2023/12/SERGIO-ANTAO-Avaliacao-de-bens-25-anos.pdf)). Isso é diferente do PTAM do COFECI (seção 5).

## 2. Fatores de homogeneização na prática (IBAPE-SP)

- **Fator oferta / fonte [S].** Norma IBAPE-SP 2011, §10.1: descontar a superestimativa do preço de oferta pelo fator médio observado no mercado. Onde não puder ser medido, usar o consagrado 0,9 (desconto de 10%). Todos os outros fatores são aplicados depois deste. A norma do Instituto de Engenharia 2019 (capital de SP), §4.7.2, faz de 0,90 o padrão, e qualquer outro valor tem de ser demonstrado. Maia Neto dá faixa de 0,80–1,00. Fonte: [Mantovani, Cymrot, Cappellano, COBREAP, estudo de Atibaia](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2020/02/PE-17-Fator-Oferta-para-Im%C3%B3veis-Residenciais-da-Cidade-de-Atibaia.pdf).
  - Esse estudo mediu média real de **0,93** (desconto de 7%). Por padrão construtivo: 0,94 médio, 0,93 superior, 0,92 fino.
  - Recomenda coletar tempo de mercado e anúncios vendidos e não vendidos.
  - [Syn] Os dados próprios da One (oferta vs fechamento) podem medir esse fator diretamente para a Granja Viana — exatamente o que a norma prefere ao padrão 0,90.
- **Requisitos da NBR para qualquer fator [S]** (item 8.2.1.4.2, segundo [Cappellano/IBAPE](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2026/03/ix-seminario-nacional-de-engenharia-de-avaliacoes-e-pericias-desmistificando-o-uso-de-fatores-cappellano.pdf)):
  - calculado por método científico;
  - regional e datado, revisto no máximo a cada 4 anos;
  - publicado por entidades regionais reconhecidas, universidades ou entes públicos;
  - metodologia anexada ao laudo.
  - A norma IBAPE-SP agrupa os fatores:
    - Obrigatórios: oferta, localização, profundidade, testada, área, frentes múltiplas, idade, padrão.
    - Complementares, exigindo dupla validação: topografia, consistência.
  - Fatores deduzidos para a cidade de SP e usados em outras praças são criticados em [Nasser Jr.](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2026/01/radegaz-junior.pdf).
  - [Syn] Tabelas de zona da capital não se transferem automaticamente para Cotia.
- **Terrenos [S]** (de um laudo usando as tabelas IBAPE-SP 2005, [CPCON](https://static.suporteleiloes.com.br/lutheroleiloescombr/bens/10946/arquivos/sl-bem-10946-6a95cbe7b4e6b-6a95cbe7b710c.pdf)):
  - Testada: F = (Fp/Fr)^f, válido para Fr/2 ≤ Fp ≤ 2Fr.
  - Profundidade: (Pe/Pmi)^p quando ½Pmi ≤ Pe < Pmi. Quando Pma < Pe ≤ 3Pma: Pma/Pe + [1 − Pma/Pe]·(Pma/Pe)^p.
  - Expoentes e valores de referência dependem da zona, pelas tabelas 1–2 da norma. **Tabelas não obtidas [NV].**
  - A tabela de proporção de área do mesmo laudo tem passo de −0,05 por duplicação: 500 m² = 0,95, 1.000 = 0,90, 2.000 = 0,85, etc.
  - Topografia nesse laudo: plano 1,00. Em declive para o fundo: até 5% = 0,95, 5–10% = 0,90, 10–20% = 0,80, acima de 20% = 0,70.
  - O exemplo de Cappellano usa 0,90 para terreno 2 m acima da rua, faixa 0,70–1,00.
- **Padrão construtivo e idade [S].** O estudo IBAPE-SP "Valores de Edificações de Imóveis Urbanos" dá coeficientes de padrão relativos ao R8N; o exemplo de Cappellano usa "padrão fino" = 4,399, faixa 3,865–4,843.
  - Depreciação por Ross-Heidecke: Foc = R + K·(1 − R). R = valor residual pelo padrão. K vem da razão idade/vida útil e do estado de conservação.
  - Exemplo: 0,2 + 0,221·0,8 = 0,377 ([documento judicial via busca](https://static.suporteleiloes.com.br/leilaobrasil/leiloes/lotes/anexos/65dcdeb42cece.pdf)).
  - Tabelas R e K não obtidas [NV].
  - Limitação conhecida: Ross-Heidecke funciona mal para edificações mais velhas que a vida útil de referência ([Confea/Contecc 2022](https://www.confea.org.br/midias/uploads-imce/Contecc%202022/Civil/AVALIA%C3%87%C3%83O%20DE%20IM%C3%93VEIS%20COMERCIAIS%20COM%20A%20INFLU%C3%8ANCIA%20DE%20MANIFESTA%C3%87%C3%95ES%20PATOLOGICAS%20UTILIZANDO%20O%20M%C3%89TODO%20DE%20ROSS-HEIDECKE.pdf)).

## 3. Abordagens estatísticas e de ML (AVMs)

- **Zillow Zestimate [S].** Rede neural alimentada por registros fiscais e feeds de MLS. Entradas incluem comparáveis e dias no mercado.
  - Erro mediano nacional de 6,9% após o upgrade de 2021 (release, via [Zillow](https://www.zillow.com/zestimate/)).
  - Fontes secundárias citando a página da Zillow dão ~1,8–1,9% on-market e ~7,0% off-market ([TheClose](https://theclose.com/how-accurate-is-zillow-zestimate/)). A página da Zillow devolveu 403, então os decimais exatos são [NV].
  - [Syn] O erro on-market é baixo porque o preço anunciado é uma entrada. O off-market é a referência honesta.
- **Redfin Estimate [S]:** erro mediano 1,89% on-market e 7,43% off-market. Usa "500+ data points" e "nearby homes that recently sold and have similar features" ([Redfin](https://www.redfin.com/redfin-estimate)).
- **Brasil [S]:**
  - Árvores com boosting sobre ~15.000 anúncios raspados: **erro absoluto mediano de 8,16%**. Os autores dizem também que bancos brasileiros avaliam com regressão linear e não testam seu desempenho preditivo ([Marzagão et al., RBE 2021](https://periodicos.fgv.br/rbe/article/view/79823)).
  - DataZap (grupo OLX) tem um AVM comercial integrado à ferramenta de garantias da B3. Cobre apartamentos em 300+ cidades e **não publica métrica de erro** ([Monitor Mercantil](https://monitormercantil.com.br/datazap-passa-a-integrar-gestao-de-garantias-da-b3/), [Baguete](https://www.baguete.com.br/noticias/zap-cria-area-de-inteligencia)).
  - Loft: nenhuma métrica de erro publicada ([Bloomberg Línea](https://www.bloomberglinea.com.br/2023/05/19/na-loft-o-uso-de-dados-para-prever-precos-e-demanda-e-aposta-para-vender-imovel/)).
  - QuintoAndar: nada público encontrado.
  - Uma tese USP compara modelos hedônico, kNN e XGBoost em apartamentos de SP ([USP](https://teses.usp.br/teses/disponiveis/3/3142/tde-10072024-115640/publico/FlaviodeFalcaoeHelenaOrig23.pdf)).
  - Na literatura, ensembles de árvores costumam vencer modelos hedônicos lineares quando há muitos dados.
- **Como reportar confiança [S]:**
  - Desvio-padrão da previsão (FSD): com FSD = 10%, ~68% dos preços reais caem dentro de ±10% ([Freddie Mac](https://my.sf.freddiemac.com/docs/pdf/fact-sheets/dougwhitepaper_metricsmatter.pdf)).
  - O "Common Confidence Score" MISMO é a probabilidade de o valor do AVM estar dentro de 10% do valor de mercado.
  - IVS/RICS exigem documentar por que um modelo foi escolhido e validar sua saída ([Cardoso/IBAPE](https://biblioteca.ibape-nacional.com.br/wp-content/uploads/2025/02/Use-of-Valuation-Models-under-IVS-RICS-and-USPAP-Carlos-Cardoso.pdf)). Texto do padrão RICS de AVM não acessado [NV].
- **Seleção de comparáveis [S]:** Fannie Mae B4-1.3-08: comparáveis devem casar com o avaliando em terreno, nº de cômodos, área acabada, estilo e conservação. Vendas no mesmo bairro são o indicador mais forte; comparáveis de áreas concorrentes devem ser sinalizados e justificados ([Fannie Mae](https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales)). O mínimo de "3 vendas fechadas em 12 meses" aparece só em fontes secundárias [NV].

## 4. Negócios que falharam como sinal

- **[S] Knight (2002), *Real Estate Economics* 30(2):213–237.** Imóveis com markup inicial alto e imóveis vagos são os mais propensos a ter o preço cortado. Cortes percentuais maiores levam a mais tempo de mercado e preço final menor; o erro de precificação inicial custa tempo e dinheiro ([RePEc](https://ideas.repec.org/a/bla/reesec/v30y2002i2p213-237.html)).
- **[S] Genesove & Mayer (2001, *QJE*).** Proprietários diante de perda nominal anunciam 25–35% dessa diferença acima, acabam vendendo 3–18% dela acima, e têm hazard de venda bem menor ([NBER w8143](https://nber.org/papers/w8143)).
  - [Syn] Registrar o preço e data de compra do vendedor quando conhecidos. Prevê sobrepreço.
- **[S] Haurin et al. (2010):** preço anunciado vs preço de venda vs tempo de comercialização ([RePEc](https://ideas.repec.org/a/bla/reesec/v38y2010i4p659-685.html)).
- **Modelos de sobrevivência [S].** A Opendoor mostra que descartar anúncios não vendidos ou retirados enviesa modelos de tempo até a venda. A correção é um modelo de hazard em tempo discreto sobre linhas anúncio-dia, com preço atual, estoque concorrente e sazonalidade como covariáveis. Saídas: probabilidade diária de venda, dias esperados até a venda e taxa de escoamento ([Opendoor](https://www.opendoor.com/articles/liquidity-modeling-real-estate-survival-analysis)).
  - A literatura acadêmica trata a retirada como censura ou risco competidor.
  - Um estudo holandês de riscos competidores mostra que o hazard de venda cai com a duração e o de retirada sobe ([ERES](https://eres.architexturez.net/node/19260) e [Springer JORS](https://link.springer.com/article/10.1057/jors.2011.74)).
- **[Syn] Sinais a calcular do pipeline próprio:**
  - razão anunciado/vendido, segmentada;
  - dias no mercado, com anúncios ativos e retirados como censurados;
  - número e tamanho de cortes de preço;
  - anúncios "parados", i.e. retirados ao preço P — evidência de que P está acima do mercado;
  - absorção = fechamentos ÷ estoque ativo por segmento.
  - Um anúncio retirado a P é uma observação de **limite superior**. Não é preço comparável.

## 5. Dados públicos e quadro regulatório

- **ITBI.**
  - A cidade de São Paulo publica as declarações de ITBI pagas desde 2019, com identificação do imóvel, endereço, valor da transação e cartório (sem nomes das partes). A Lei 18.161/2024 tornou isso dever legal ([IRIB](https://www.irib.org.br/?p=47773), [CNB-SP](https://cnbsp.org.br/2022/08/01/prefeitura-de-sao-paulo-prefeitura-de-sao-paulo-recebe-doacao-de-dados-sobre-transacoes-imobiliarias/)).
  - **Para Cotia e Carapicuíba não foi encontrado dataset de ITBI publicado [NV].** Pedido via LAI é uma opção.
  - [S] STJ Tema 1113 (REsp 1.937.821/SP, 2022): a base do ITBI é o valor de mercado. Não está atrelada ao IPTU, o IPTU não pode ser piso, e o município não pode impor valor de referência prévio. O valor declarado presume-se valor de mercado ([boletim TRF1](https://www.trf1.jus.br/trf1/conteudo/files/Boletim%20NUGEP%2008%202022.pdf)).
  - [Syn] Por essa presunção, valores declarados de ITBI podem estar subdeclarados. Usar com cuidado.
- **Planta Genérica de Valores (Cotia).** Não encontrada online [NV]. Pelo STJ é ferramenta só de IPTU. [Syn] Útil no máximo como índice relativo de localização.
- **FipeZap [S].** Cobre **só apartamentos** ("apartamentos prontos"), de anúncios, em 56 cidades. Barueri (R$10.462/m²) e Osasco (R$7.661/m²) estão incluídas; **Cotia e Carapicuíba não** (relatório FipeZap jul/2024, [PDF DataZap](https://www.datazap.com.br/wp-content/uploads/2024/08/fipezap-202407-residencial-venda.pdf)).
  - [Syn] No máximo proxy de tendência temporal regional. Não é referência de nível para casas em condomínio.
- **IBGE [S].** Censo 2022 "Agregados por Setores Censitários" inclui renda do responsável. Setores com menos de 5 domicílios são suprimidos ([IBGE](https://biblioteca.ibge.gov.br/visualizacao/livros/liv102136.pdf)).
  - [Syn] Utilizável como covariável de localização/renda.
- **Raspagem de portais (Zap/VivaReal/OLX).** A página de termos do Zap devolveu 403, então **os ToS não foram verificados [NV].** Uma nota jurídica do Demarest discute a legalidade de scraping no Brasil ([Demarest](https://www.demarest.com.br/wp-content/uploads/2022/01/Web-scraping-legal-ou-ilegal-1.pdf)).
  - [Syn] Tratar como risco jurídico: ToS, direito sobre bases de dados e LGPD se capturar dados de corretor/proprietário. Preferir feed licenciado (DataZap) ou comparáveis inseridos manualmente.
- **PTAM e CNAI [S].** Resolução COFECI 1.066/2007 ([NormasBrasil](https://www.normasbrasil.com.br/norma/resolucao-1066-2007_105572.html)):
  - Art. 6: qualquer corretor pessoa física inscrito no CRECI pode elaborar PTAM. Uma pessoa jurídica inscrita pode patrocinar, mas um corretor pessoa física deve assinar.
  - Art. 2: o CNAI (Cadastro Nacional de Avaliadores Imobiliários, do COFECI) exige formação superior em gestão imobiliária ou certificado de curso de avaliação reconhecido pelo COFECI. O COFECI pode exigir exame.
  - Art. 5: conteúdo mínimo do PTAM — solicitante, finalidade, metodologia, valor com data de referência, identificação/currículo/assinatura do avaliador, mais matrícula, endereço, medidas, confrontações e data da vistoria.
  - A ABNT 14653 aparece só no preâmbulo.
  - Entidades de engenharia (IBAPE/CONFEA) contestam a competência dos corretores. A posição do CRECI-ES é que os tribunais decidiram a favor dos corretores ([CRECI-ES](https://crecies.gov.br/avaliacao-de-imoveis-deve-ser-feita-por-corretor-de-imoveis), fonte de classe).
  - Ambiguidade: uma busca disse que a Res. 957/2006 foi revogada pela Res. 1.064, não pela 1.066 [NV]. Confirmar no site do COFECI.
  - [Syn] A saída da ferramenta deve ser enquadrada como sugestão de preço ou minuta de PTAM para um corretor CNAI revisar e assinar. Não é "laudo" NBR 14653, que é território de engenharia.

## 6. Contexto de mercado da Granja Viana

- **Não existe índice público para casas em condomínio na Granja Viana [S, achado negativo].**
- Preços pedidos pontuais em anúncios dão ~R$5.700–9.200/m² para casas e ~R$570/m² para um terreno em condomínio (anúncios Zap, VivaReal e Loft, calculado pela ferramenta de busca). São pedidos anedóticos, não estatística de mercado. Não usar.
- Lançamentos de apartamentos na Granja Viana: média ~R$6,7–7,2 mil/m² ([apto.vc](https://apto.vc/br/sp/cotia/granja-viana)).
- "Granja Viana" abrange endereços de Cotia, Carapicuíba e Jandira — normalizar o campo de município.
- Os vetores citados pelo dono (condomínio específico, acesso à Raposo Tavares, escolas, segurança) **não têm fonte** [Syn]. Os negócios próprios terão de quantificá-los. A principal variável de localização provavelmente é "qual condomínio", tratada como efeito fixo.

## 7. Arquitetura para poucos dados [Syn]

Com centenas de negócios próprios espalhados em segmentos (casas, terrenos, comercial), um AVM puramente de ML não generaliza nem é defensável. O padrão defensável é **comparáveis no formato NBR, estatística ajustada nos dados próprios e faixa honesta**.

## Abordagem recomendada para a One Consultoria [Syn]

1. **Modelo de dados.** Um histórico `deal_events` por imóvel:
   - data de captação, preço inicial, cada mudança de preço, desfecho (fechado / retirado / expirado / ativo), preço e data de fechamento;
   - atributos: m² de terreno, m² construído, padrão, idade, conservação, ID do condomínio, testada/profundidade/declive do terreno, suítes, desocupação, e preço de compra do vendedor se conhecido.
   - Guardar um campo `source`: own-closed, own-failed, external-listing, ITBI.
2. **Motor A, primário e explicável: comparáveis + tratamento por fatores, modelado na Tabela 4 da NBR.**
   - Selecionar comparáveis por kNN com distância ponderada: mesmo condomínio, depois cluster vizinho, depois área/padrão/idade, com decaimento por recência.
   - Converter oferta em transação com **fator oferta medido nos dados próprios** por segmento (mediana fechamento ÷ último preço pedido, com IC). Cair para 0,90 só quando n for pequeno, e dizer isso.
   - Ajuste temporal com índice simples ajustado nos fechamentos próprios; FipeZap Barueri/Osasco só como proxy, sinalizado.
   - Aplicar poucos fatores (área, padrão, idade/conservação; testada/profundidade/declive para terrenos). Limitar cada fator à faixa 0,80–1,20 do Grau II e descartar comparáveis que precisem de mais.
   - Saída: média saneada, amplitude do IC 80%, lista de comparáveis com os fatores de cada um, e o grau que o resultado *alcançaria* (n ≥ 6 → II, n ≥ 12 → III) como selo de qualidade, não alegação legal.
3. **Motor B, secundário: regressão hedônica log-linear por segmento.** Só quando n ≥ 4(k+1) (piso do Grau II) e todos os coeficientes passarem nos limites de significância; senão devolver "dados insuficientes", sem fallback silencioso. Mostrar coeficientes como explicações em linguagem simples ("+1 suíte ≈ +x%").
4. **Motor C, camada de negócios que falharam.**
   - Um modelo de hazard em tempo discreto (regressão logística sobre semanas-de-anúncio; linhas censuradas mantidas) estima P(venda em 90/180 dias) em função de preço pedido ÷ valor do motor A.
   - Preços pedidos de anúncios retirados/expirados funcionam como limites superiores.
   - Resultado: dois números — a faixa de "valor de mercado" e um **preço de anúncio recomendado** com tempo esperado de mercado. Corretores agem sobre o segundo.
5. **Gradient boosting.** Adiar até ~1.000+ fechamentos rotulados ou feed externo licenciado. Se adicionado, reportar MdAPE, P(dentro de ±10%) em holdout temporal e explicações SHAP, e nunca como motor único.
6. **Validação.** Backtest mensal nos fechamentos próprios: MdAPE e taxa de acerto dentro de ±5/±10%. Publicar essas métricas na UI ao lado de cada sugestão. Referências: erros off-market Zillow/Redfin ~7%, modelo brasileiro de anúncios de Marzagão 8,16%.
7. **Saída.**
   - Faixa (baixo/central/alto) com amplitude do IC e comparáveis.
   - O fator oferta medido.
   - O risco de tempo longo de mercado.
   - Ressalvas explícitas.
   - Opcional: "exportar como minuta de PTAM" preenchida com os campos do Art. 5 da Res. 1.066 para um corretor CNAI revisar e assinar.
8. **Faseamento.**
   - Primeiro: Motor A + medição do fator oferta.
   - Depois: Motor C.
   - Motor B por segmento quando os dados permitirem.
   - ML por último.

## Decisões em aberto para o dono (lista original da pesquisa)

1. **Enquadramento jurídico.** Saída interna apenas, ou PTAM para o cliente? Se PTAM, qual corretor CNAI assina, e a ferramenta fica posicionada só como minuta?
2. **Dados externos.** Licenciar DataZap ou similar (custo), raspar portais (risco ToS/jurídico, precisa de advogado), ou inserir comparáveis à mão?
3. **Esforço em dados públicos.** Pedido LAI a Cotia e Carapicuíba pelos dados de transação de ITBI?
4. **Backfill histórico.** Quantos negócios passados, incluindo retirados com preços e datas, podem ser reconstruídos, e quem é dono da limpeza?
5. **Segmentação.** Quais segmentos recebem a ferramenta primeiro (casas em condomínio, terrenos, comercial)? Comercial provavelmente exige método da renda e pode ficar fora.
6. **Política do fator oferta.** Usar o desconto medido mesmo que difira do padrão 0,90? Em que janela de tempo, e com que frequência re-medir?
7. **Apresentação da faixa.** Mostrar o IC 80% completo, a faixa de arbítrio de ±15%, ou ambos? Mostrar um valor separado de "preço de anúncio para X dias"?
8. **Dado de psicologia do vendedor.** Registrar preço e data de compra do vendedor (sinal Genesove-Mayer) sob consentimento LGPD?
9. **Lista mestre de condomínios.** Criar lista canônica de condomínios com atributos (segurança, lazer, acesso) para a localização virar variável confiável?
10. **Comprar as normas.** Comprar a NBR 14653-1/-2 (e a norma IBAPE-SP com suas tabelas de fatores) para confirmar os limiares marcados [NV] antes do go-live?

Respostas já dadas pelo dono → [`DECISIONS.md`](DECISIONS.md).

---

## Anexo A — Sondagem da API Vista (2026-10-14, somente status, nenhum dado de cliente lido)

Script read-only via `VistaClient.probe` / `detalhes_imovel` sobre o tenant `oneconsu-rest`:

| Superfície | Resultado |
|---|---|
| `/imoveis/historicos` | 404 not_found |
| `/negociacoes/listar` | 404 not_found |
| `/propostas/listar` | 404 not_found |
| `/vendas/listar` | 404 not_found |
| campo `DataVenda` | REJEITADO (VistaFieldNotAvailable) |
| campo `ValorVendido` | REJEITADO |
| campo `Vendido` | REJEITADO |
| campo `DataFechamento` | REJEITADO |
| campo `ValorAnterior` | REJEITADO |
| campo `DataSaida` | REJEITADO |
| campo `Inativo` | REJEITADO |
| campo `Situacao` | aceito (tem valor) |
| campo `ExibirNoSite` | aceito (tem valor) |
| campo `DataAtualizacao` | aceito (tem valor) |

Conclusão: **a API Vista não entrega preço de venda, data de venda nem histórico de preço.** `/imoveis/listar` só retorna anúncios ativos (`Status` enum = Aluguel / Venda / Venda e Aluguel). Ver também `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` (Tier-2 questions: `negociacoes/*`, `propostas/*`, `vendas/*`; suspeita de versão de API diferente). Interface web do CRM: `https://crmx.novovista.com.br/` (Vista agora é "Loft/CRM") — exploração via navegador só com o "vai" do dono e login feito por ele.

## Anexo B — O que o código do SW já tem (mapa de 2026-10-14)

**FE** (`products/social-wiring/frontend/src`)
- Grupo de nav "Imóveis": `nav/navGroups.ts:91-99` (`/imoveis`, `/permutas`). `imoveis` semeado como `'desenvolvimento'` em `migrations/040_imoveis.sql:196-198`.
- Rotas `App.tsx:206-208`: `/imoveis` → `pages/Imoveis.tsx`; `/imoveis/:codigo` → `pages/ImovelDetalhes.tsx`.
- Página de detalhe: coluna direita do cabeçalho (linhas ~220-270) com `valor_venda` e o botão "Solicitar campanha" — lugar natural do botão "Sugestão de preço". Painel de resultado: card novo ao lado de `ImovelSimilaresCard` (linha ~500) ou abaixo de `ImovelValoresSection`.
- Hooks: `hooks/useImoveis.ts` (`useImovel`, `formatValor`), `hooks/useImovelRelacionamentos.ts` (`useImovelSimilares`).

**BE** (`products/social-wiring/backend`)
- `app/routers/imoveis_router.py` (lista via view `imoveis_catalogo`, detalhe `/{codigo}`), `app/modules/imovel_hub/` (captação manual, dados, documentos, duplicatas, `similares_service.py`).
- Tabelas: `imoveis` (espelho Vista, PK `(org_id, codigo)`, 040 + 093), `imovel_registry` (063; `delistado_em`, `snap_valor_venda`…), `imovel_captacao` (226, manuais), `imovel_dados` (075+; matrícula, endereço manual, `processo_atual_numero`), view `imoveis_catalogo` (226 → 228).
- **Novo (2026-10-14):** `imovel_preco_historico` (migração 262) — histórico append-only de preço pedido via triggers em `imoveis` e `imovel_captacao`, com baseline; `atendimentos.motivo_perda`.

**Colunas relevantes e fraquezas**
- Preço: `valor_venda`, `valor_locacao`, `valor_condominio`, `valor_iptu`.
- Áreas: `area_total`, `area_privativa`, `area_construida` (**"0"/NULL em 1918 de 1919 linhas**), `area_terreno` (preenchido em 3 de 20 amostras), `frente`, `fundos`.
- Cômodos: `dormitorios`, `suites`, `vagas`; banheiros só como flag `banheiro_social` (contagem `Banheiros` negada pelo tenant).
- Localização: bairro, cidade, cep, logradouro, `empreendimento`, lat/long (**ausentes em 36,8%**).
- Idade/estado: `ano_construcao` (16/20 amostras), `situacao`; **não há coluna de padrão construtivo**.
- `status` = tipo de transação, **não** vendido/disponível.
- O sync diário faz upsert e nunca apaga: imóveis deslistados continuam em `imoveis` com `sincronizado_em` antigo; o pool de similares não os filtra.

**Negócios (preços reais de fechamento)**
- `atendimentos` (status aberta/aceita/perdida, `closed_at`); ganho = `status='aceita' AND closed_at IS NOT NULL`.
- `atendimento_negociacao.valor_negociado` (preço real acordado) + `imovel_codigo` (FK para `imovel_registry`).
- `atendimento_propostas` (`valor_proposto`, status, `motivo_recusa`, datas), `processos_venda.valor`, `atendimento_imoveis` (181), `pipeline_movimentos`.
- `lead_vendas`: 0 linhas em prod (2026-08-25).
- **O FE do SW não tem ação "marcar como perdida"** — nenhuma tela chama `POST /atendimentos/{id}/perder`; logo nenhum negócio perdido jamais foi registrado.

**Reaproveitável**
- Motor de similares: `similares_service.py` + `noctusai_lib/domain/real_estate/matching.py` (`gerar_matches_para_imovel`; pesos região 30 / preço 25 / specs 20 / interesses 15 / qualidade 10). Usa preço como entrada → enviesado para avaliação; precisa de variante sem preço.
- Template de "sugerir preço" com LLM: `products/erp-imobiliario/backend/app/services/ai_service.py:284-368` (`suggest_price` → `{preco_sugerido, faixa_min, faixa_max, analise}`), router `ai.py:141-189`, consentimento `erp.suggest_price` — produto **adormecido**.
- Padrão LLM do SW: `noctusai_lib.integrations.llm.chat_completion` + `enforce_budget`; saídas em `social_wiring.ai_outputs` / `ai_feedback` (239; `ref_id` UUID → usar `imovel_registry.id`).

**Volumes (de docs, sem consulta a prod)**
- Catálogo: 1919 imóveis (2026-08-03), 2057 (2026-09-04). Venda 89,4%, Venda e Aluguel 7,2%, Aluguel 3,4%. Casa em Condomínio 1308, Terreno em Condomínio 294, Apartamento 101; 18 cidades, 428 bairros; `DataCadastro` 2012–2026.
- Leads com código de imóvel: 11.375; 63% (1019 códigos distintos) apontam para imóveis fora do catálogo.
- Contratos: 22 em prod. Org única: ONE CONSULTORIA IMOBILIÁRIA LTDA; tenant Vista `oneconsu-rest`.
