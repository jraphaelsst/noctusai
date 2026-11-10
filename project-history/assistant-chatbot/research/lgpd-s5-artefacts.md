# Assistant: linha pessoal de WhatsApp, artefatos LGPD da S5

> Rascunho do `legal-advisor` (somente leitura), 10/11/2026, para revisão e assinatura do dono, de um advogado (OAB) e do encarregado. **É orientação, não parecer jurídico.** Nenhum arquivo foi alterado.
>
> **Vale para:** 10/11/2026 · LGPD (Lei 13.709/2018) · Res. CD/ANPD 2/2022, 15/2024, 18/2024 e 19/2024 · produto `products/assistant` · linha pessoal de WhatsApp do dono via WAHA (cliente não oficial) · escopo da revisão 2 do plano (`phase0-d46-shadow-line.md` §6). Esse escopo é: só classificação ("é sobre agendamento?"), sem resposta-sombra, só mensagens recebidas em conversas 1:1, sem grupos, status ou transmissões, só daqui para frente a partir do pareamento (`paired_at`), só texto para o LLM, lista de exclusão e acesso só do administrador.
>
> **Como ler as citações.** Cada citação traz o nível da fonte e a data de leitura:
> - **[norma]**: texto oficial da lei ou resolução.
> - **[órgão oficial]**: guia ou página da ANPD ou do governo.
> - **[publicação profissional]**: escritório de advocacia ou imprensa especializada.
> - **[em aberto]**: sem fonte confiável; vai para a lista do advogado.
>
> Leitura das fontes:
> - LGPD: relida no Planalto em 10/11/2026.
> - Res. 19/2024 no DOU: a página não abriu hoje (conexão caiu duas vezes). O texto usado é o lido no DOU em 05/11/2026 e registrado no KB `PATTERNS/legal/lgpd-privacy-program.md` §9.
> - Termos do WhatsApp: relidos em 10/11/2026.
> - Documentação da OpenAI e da Anthropic: lida em 10/11/2026.
>
> **Placeholders.** Onde aparece `[PREENCHER: …]`, só o dono sabe o dado. Nenhum dado pessoal real aparece neste documento.

---

## 0. Pontos que mudaram desde o relatório anterior (leia primeiro)

1. **Existe agora uma decisão de adequação Brasil–UE**, a Res. CD/ANPD 32/2026, de 26/01/2026, com decisão recíproca da Comissão Europeia [publicação profissional: Lefosse, Mattos Filho, Cescon Barrieu; texto no DOU não lido; confirmar].
   - Ela **não cobre os EUA**.
   - Abre um caminho novo para a transferência: usar a **região Europa** do provedor de LLM. A OpenAI oferece "Europe (EEA + Switzerland)" via `eu.api.openai.com`, mas exige aprovação de controles de abuse monitoring e uma emenda contratual ("Modified Retention") [órgão oficial do fornecedor: documentação da OpenAI, lida em 10/11/2026].
   - Nesse caso, o mecanismo passaria a ser o art. 33, I (país adequado), e não as cláusulas-padrão. **Decisão do advogado** (ver §7).
2. **Retenção nos provedores de LLM** [documentação dos fornecedores, lida em 10/11/2026]:
   - **OpenAI:** não treina com dados da API por padrão. Guarda logs de abuso por "up to 30 days". Retenção zero (ZDR) só com aprovação prévia.
   - **Anthropic:** não treina sem permissão expressa. ZDR por acordo, organização por organização. Alguns modelos exigem retenção de 30 dias. A retenção padrão aparece de formas diferentes em páginas diferentes, então vale o que estiver no DPA (Data Processing Addendum) vigente.
3. **Correção de citação do relatório anterior.** Na versão de 04/01/2021 dos Termos do WhatsApp (a vigente em 10/11/2026), não achei literalmente a frase "acessar o serviço por meios automatizados ou não autorizados". O texto real proíbe:
   - "(c) gain or attempt to gain unauthorized access to our Services or systems";
   - "(e) create accounts for our Services through unauthorized or automated means";
   - "(f) collect information of or about our users in any impermissible or unauthorized manner";
   - "(i) create software or APIs that function substantially the same as our Services".

   E o WhatsApp pode "modify, suspend, or terminate your access … anytime for any reason". A conclusão (risco contratual real de perder a conta) não muda. A citação do termo de aceite (§6) usa o texto correto.
4. **Ainda não há regulamento da ANPD sobre direitos dos titulares.** O tema segue na agenda regulatória 2025–2026 (minuta em consulta interna de maio a junho de 2025) [publicação profissional e órgão oficial, busca de 10/11/2026]. Os prazos continuam sendo os da própria LGPD (§5).

---

## 1. Teste de legítimo interesse (LGPD art. 10)

**TESTE DE LEGÍTIMO INTERESSE: Assistant, classificação de mensagens recebidas na linha pessoal de WhatsApp**
Versão 1 · [PREENCHER: data] · Controlador: [PREENCHER: razão social e CNPJ da NoctusAI, **ou**, se ainda não houver CNPJ, nome do dono "na qualidade de empresário/controlador" e CPF só no documento assinado]
Elaborado por: legal-advisor (rascunho) · Revisado por: [PREENCHER: advogado, OAB nº] · Parecer do encarregado: [PREENCHER]

Base: LGPD art. 7, IX e art. 10 [norma, Planalto, lida em 10/11/2026]. Método em 3 fases do Guia de Legítimo Interesse da ANPD (fev/2024) [órgão oficial, lido via KB em 05/11/2026].

**Fase 1: finalidade (legitimidade do interesse)**
- **Interesse:** saber se um classificador automático identifica corretamente mensagens sobre agendamento (marcar, remarcar, desmarcar compromissos). O resultado serve de base para decidir se o produto Assistant segue adiante.
- **Situação concreta:** o art. 10, caput, exige finalidades "consideradas a partir de situações concretas". O caso é o "apoio e promoção de atividades do controlador" (art. 10, I).
- **Licitude:** o interesse é lícito, específico e atual. Ele não é especulativo.
- **Fica de fora da finalidade:** responder a ninguém, perfilar pessoas, vender ou compartilhar dados, treinar modelos de terceiros e decidir qualquer coisa sobre o titular. Por isso o art. 20 não se aplica nesta fase.

**Fase 2: necessidade (art. 6, III; art. 10 §1)**
- **Coletamos só o que a avaliação exige:**
  - texto de mensagens **recebidas** em conversas **1:1**;
  - só a partir do pareamento;
  - identificador do remetente **pseudonimizado** (HMAC com chave separada);
  - data e hora.
- **Não coletamos:**
  - mensagens enviadas pelo dono;
  - grupos, status e listas de transmissão (descartados antes de gravar);
  - histórico anterior ao pareamento;
  - mídia (áudio, imagem, documento: só a marca `skipped`);
  - nome do contato e foto;
  - contatos da lista de exclusão.
- **Alternativas consideradas:**
  - *Dados sintéticos:* não reproduzem a linguagem real de agendamento. Insuficientes para medir precisão.
  - *Pedir consentimento a cada interlocutor:* inviável, porque são contatos espontâneos e imprevisíveis.
  - *Exportar e rotular manualmente conversas antigas:* exige histórico, o que é mais invasivo.

  Conclusão: a amostra real, mínima e daqui para frente é o meio menos invasivo que atende à finalidade.
- **O LLM recebe** só o texto da mensagem. Não recebe número nem nome.

**Fase 3: balanceamento e salvaguardas**
- **Expectativa legítima do titular** (é o ponto mais fraco do teste):
  - quem escreve ao dono espera que o dono leia, e talvez que um assistente ajude;
  - não espera que a mensagem vá para um fornecedor de IA nos EUA para avaliar um produto.

  O que compensa:
  - transparência ativa: recado do WhatsApp com link e seção no aviso de privacidade (§4);
  - nenhum efeito sobre o titular, que não recebe resposta e sobre quem nada se decide;
  - volume pequeno;
  - retenção curta;
  - exclusão e oposição fáceis.
- **Riscos aos direitos:** vazamento de conversas privadas, conteúdo sensível incidental (art. 11) e transferência internacional. Ver RIPD (§3).
- **Salvaguardas obrigatórias** (condição deste teste):
  - (i) filtros de entrada já citados;
  - (ii) HMAC do número, com chave em cofre separado;
  - (iii) brutos apagados em 90 dias e conjunto de avaliação em ≤12 meses, com exclusão automática registrada (§5);
  - (iv) acesso só do administrador, com RLS e log de leitura;
  - (v) API comercial sem treino, retenção mínima ou zero pedida ao provedor, mecanismo de transferência válido;
  - (vi) mensagem com conteúdo sensível ou de criança/adolescente sai do conjunto de avaliação;
  - (vii) zero escritas no WhatsApp: nada de envio, "visto", presença ou digitação (três camadas do plano, item 1);
  - (viii) canal para pedidos de titulares, com oposição atendida colocando o número na lista de exclusão (art. 18 §2);
  - (ix) nada de conteúdo real em logs, commits ou memória.
- **Resultado:** [ ] favorável · [ ] favorável com condições · [ ] desfavorável. Recomendação do rascunho: **favorável com condições**, as salvaguardas (i) a (ix) acima, mais a resolução da transferência internacional (§7, item 4) antes do pareamento da linha pessoal.
- **Revisão obrigatória** quando houver: resposta-sombra ou envio real, novo provedor de LLM, inclusão de mídia ou grupos, incidente, ou mudança de finalidade.

Assinaturas: Controlador [PREENCHER] · Encarregado [PREENCHER] · Advogado [PREENCHER, OAB] · Data [PREENCHER]

---

## 2. Entrada no ROPA (LGPD art. 37)

O art. 37 exige registro "especialmente quando baseado no legítimo interesse" [norma, Planalto, 10/11/2026]. Como o tratamento é de alto risco (§3), não usar o ROPA simplificado de agente de pequeno porte (Res. 2/2022 arts. 3–4 e 9) [norma, via KB em 05/11/2026].

| Campo | Valor |
|---|---|
| ID | `assistant-linha-pessoal-classificacao` |
| Produto | `products/assistant` |
| Papel da NoctusAI | Controlador |
| Controlador | [PREENCHER: razão social + CNPJ, ou dono como empresário] · endereço [PREENCHER] |
| Encarregado | [PREENCHER: nome] · contato [PREENCHER: e-mail do canal do titular] · ato de nomeação [PREENCHER: data] · substituto [PREENCHER] |
| Finalidade | Avaliar um classificador "é sobre agendamento?" em mensagens recebidas, para decidir a viabilidade do produto Assistant |
| Base legal | Art. 7, IX (legítimo interesse) + teste do art. 10 (§1 deste documento, v1, [PREENCHER: data de assinatura]) |
| Dados sensíveis | Não são objetivo. Podem aparecer de forma incidental. Mensagem marcada como sensível sai do conjunto de avaliação e não gera perfil (art. 11 §1) |
| Titulares | (a) Pessoas que mandam mensagem 1:1 à linha pessoal (interlocutores) · (b) o dono (rótulos que ele atribui, logs de acesso) |
| Crianças/adolescentes | Não são objetivo. Família na lista de exclusão. Mensagem identificada como de menor sai do conjunto de avaliação (art. 14) |
| Categorias de dados | (a) Texto da mensagem recebida, ID WAHA da mensagem, data e hora, HMAC do número do remetente · (b) Rótulo do dono, data, log de leitura |
| Dados não coletados | Mensagens enviadas pelo dono, grupos, status, transmissões, mídia, nome e foto do contato, histórico anterior ao pareamento |
| Fonte | O próprio titular, por mensagem enviada à linha. Coleta via WAHA, cliente não oficial, só leitura |
| Operadores e suboperadores | Supabase (banco; região [PREENCHER]) · provedor do VPS [PREENCHER: nome, país] · provedor de LLM [PREENCHER: OpenAI e/ou Anthropic] · [PREENCHER: Cloudflare, se estiver no caminho do webhook] |
| Terceiro independente | WhatsApp/Meta, controlador da própria plataforma |
| Transferência internacional | Destino [PREENCHER: EUA ou região UE do provedor] · mecanismo [PREENCHER após decisão do advogado: cláusulas-padrão da ANPD (Res. 19/2024, Anexo II) **ou** região UE + adequação (Res. 32/2026)] · página pública: §4 deste documento |
| Retenção | Mensagem bruta: 90 dias · conjunto de avaliação: até o fim da etapa L4, teto de 12 meses · lista de exclusão: enquanto vigorar · log de leitura: [PREENCHER, sugestão de 6 meses] · registro de pedido de titular: 5 anos, sem o número (§5) |
| Segurança | Acesso só do administrador (RLS + nível de acesso declarado) · log de leitura · HMAC com chave em cofre separado · webhook com HMAC obrigatório · zero escritas no WhatsApp (proxy de bloqueio, nenhuma rota de envio, `WahaClient` recusa escrita) · logs sem conteúdo · exclusão automática registrada |
| Direitos | Canal [PREENCHER] · exclusão e oposição por número (§5) |
| RIPD | Sim, §3 deste documento, v1 |
| Código | `products/assistant/…` · seed WAHA `client.py`, `ingest.py` · organs `ai_outputs`, `ai_feedback` [PREENCHER caminhos finais após a S2/S3] |
| Revisado em | [PREENCHER] |

---

## 3. RIPD resumido (LGPD art. 38)

O conteúdo mínimo vem do art. 38, parágrafo único: tipos de dados, metodologia de coleta e de segurança, e análise de medidas e mitigação [norma, Planalto, 10/11/2026]. A estrutura segue as perguntas e respostas da ANPD sobre RIPD [órgão oficial, via KB em 05/11/2026].

**RIPD: Assistant, classificação na linha pessoal: v1, [PREENCHER: data]**

1. **Identificação.** Controlador [PREENCHER] · operadores (ver ROPA) · encarregado [PREENCHER] · elaborado por legal-advisor (rascunho), revisão de [PREENCHER: advogado].
2. **Por que fazer o RIPD.** Alto risco pela referência da Res. 2/2022 art. 4:
   - critério geral: tratamento que pode afetar significativamente interesses e direitos fundamentais (conversas privadas);
   - critérios específicos: tecnologia emergente (LLM) e possíveis dados sensíveis.

   Consequências: o RIPD é recomendado antes do início, e **não há prazos em dobro** de agente de pequeno porte (Res. 2/2022 art. 3) [norma, via KB em 05/11/2026]. Além disso, o art. 10 §3 permite que a ANPD peça o RIPD quando a base é legítimo interesse [norma, 10/11/2026].
3. **Descrição e ciclo de vida.**
   - Pareamento (sessão com `markOnline=false` e `fullSync=false`).
   - Webhook com HMAC.
   - Filtro antes de gravar: só recebidas, 1:1, sem exclusão, só texto, deduplicadas pelo ID WAHA, a partir de `paired_at`.
   - Fila de intake.
   - Worker manda **só o texto** ao LLM e grava o resultado (`classified|failed|skipped_budget|skipped_excluded`) em `ai_outputs`.
   - O dono rotula às cegas (eventos `ai_feedback`).
   - Exclusão automática: 90 dias para brutos, ≤12 meses para o conjunto de avaliação.
   - Exclusão por número, a pedido.
4. **Dados e titulares.** Ver ROPA. Volume estimado: [PREENCHER: mensagens 1:1 recebidas por dia].
5. **Base legal.** Art. 7, IX, com o teste do §1. Nenhuma finalidade usa o art. 11, porque dado sensível não é objetivo e é descartado do conjunto.
6. **Necessidade e proporcionalidade.** Ver a Fase 2 do §1.
7. **Riscos e medidas.** P = probabilidade, I = impacto, R = risco residual após as medidas (B baixo, M médio, A alto).

| # | Risco ao titular | P | I | Medidas | R |
|---|---|---|---|---|---|
| R1 | Acesso indevido ou vazamento de conversas privadas | M | A | RLS só para o admin; log de leitura; chave HMAC separada; segredos fora do repositório; retenção curta; registro de incidentes (Res. 15/2024) | M |
| R2 | Conteúdo sensível incidental (saúde, religião, vida sexual) processado e guardado | A | A | Lista de exclusão (família, saúde, advogado, banco); retirada do conjunto de avaliação quando marcado; nenhum perfil; brutos em 90 dias. *Opcional, decisão do advogado:* o próprio prompt devolve `sensivel_suspeito` e, se verdadeiro, o texto bruto é apagado logo após classificar | M |
| R3 | Transferência internacional: acesso por autoridade estrangeira, retenção no provedor | M | M | API comercial sem treino; ZDR pedido; ou região UE; sem número nem nome no prompt; mecanismo válido (§7.4) | M→B com ZDR/UE |
| R4 | Quebra da expectativa de quem escreve (não sabe que há um sistema) | A | M | Recado com link; aviso de privacidade; nenhum efeito sobre o titular; exclusão e oposição simples | M |
| R5 | Escrita acidental no WhatsApp ("visto", presença, envio) revelando o sistema ou falando em nome do dono | M | M | Três camadas: proxy de bloqueio, nenhuma rota de envio, `WahaClient` recusa escrita; prova de 24 h na linha descartável antes | B |
| R6 | Desvio de finalidade (usar o conjunto para treino, marketing, perfil) | B | A | Finalidade fechada no teste e no ROPA; nova finalidade exige novo teste e novo RIPD; exclusão automática | B |
| R7 | Reidentificação do HMAC (números de telefone têm pouca entropia) | M | M | HMAC com chave secreta em cofre separado do banco; rotação documentada; nunca hash sem chave | B |
| R8 | Retenção além do necessário (o job falha em silêncio) | M | M | Job diário com evento de execução (contagens); alerta se não rodar em 48 h; teste automatizado | B |
| R9 | Webhook forjado injetando mensagens | B | M | HMAC obrigatório; o app não sobe em produção sem o segredo | B |
| R10 | Mensagens de crianças ou adolescentes | B | A | Família na exclusão; retirada do conjunto de avaliação (art. 14, melhor interesse) | B |
| R11 | Titular não consegue exercer direitos (não sabe do tratamento) | M | M | Recado, aviso, canal do encarregado, procedimento de §5 testado | B |
| R12 | Logs ou backups guardando conteúdo depois da exclusão | M | M | Logs sem corpo; janela de backup divulgada ([PREENCHER] dias); exclusão chega aos backups quando eles expiram | B |

8. **Riscos para o dono, que não são riscos ao titular.** Suspensão ou banimento da conta do WhatsApp: ver o termo de aceite (§6).
9. **Risco residual e aceite.** Residual **médio**, concentrado em R2, R3 e R4. Aceito por [PREENCHER: dono, como representante do controlador], com parecer do encarregado [PREENCHER].
10. **Gatilhos de revisão.** Resposta-sombra, envio real, mídia, grupos, novo provedor, incidente, nova norma da ANPD (direitos dos titulares, IA) e, no máximo, 12 meses.

---

## 4. Seção do aviso de privacidade: "Assistant"

> Inserir como seção própria e destacada da política em `/consent/privacy-policy` (mecanismo da casa: seed `seed/framework/frontend/src/content/consent.ts`). Não criar uma página paralela. A Res. 19/2024 permite que a página exigida pelo art. 17 §2 seja uma seção destacada da política [norma, via KB em 05/11/2026]. Ao mudar, atualizar `META.version` e `lastUpdated`.

### Assistant: mensagens recebidas no WhatsApp de [PREENCHER: nome público do dono ou "do titular da linha"]

**O que é.** O Assistant é um produto em teste da NoctusAI. Ele ajuda a organizar a agenda. Nesta fase, ele **só lê** algumas mensagens que você envia ao número [PREENCHER: número público da linha ou "à linha pessoal indicada no recado"] e verifica, com ajuda de inteligência artificial, se a mensagem trata de agendamento: marcar, remarcar ou desmarcar um compromisso. **Ele não responde nada em nome de ninguém.** Não marca suas mensagens como lidas e não decide nada sobre você.

**Quem é o responsável (controlador).** [PREENCHER: razão social, CNPJ, endereço]. Encarregado pelo tratamento de dados: [PREENCHER: nome], [PREENCHER: e-mail].

**Que dados usamos.**
- Usamos:
  - o texto das mensagens que você envia em conversa individual (1:1) a essa linha, a partir de [PREENCHER: data do pareamento];
  - a data e a hora;
  - um código que substitui o seu número (pseudonimização).
- Não usamos:
  - mensagens de grupos, status ou listas de transmissão;
  - áudios, fotos e documentos;
  - seu nome ou foto de perfil;
  - conversas anteriores a essa data.
- Alguns contatos ficam fora do processamento (lista de exclusão).

**Para quê e com que base legal.** Para avaliar se a classificação automática acerta, antes de decidir se o produto segue. A base é o **legítimo interesse** (LGPD, art. 7º, IX, e art. 10). Fizemos um teste de ponderação, disponível a pedido. Não usamos seus dados para publicidade, perfil ou treinamento de modelos de terceiros.

**Por quanto tempo.** O texto das mensagens é apagado em até **90 dias**. Uma amostra pequena, usada para medir a qualidade e sem o seu número, é guardada até o fim da avaliação, com máximo de **12 meses**, e depois apagada. As cópias de segurança são substituídas em até [PREENCHER] dias.

**Transferência internacional de dados.** Para classificar a mensagem, o **texto, sem seu número e sem seu nome**, é enviado ao provedor de inteligência artificial [PREENCHER: OpenAI, L.L.C. e/ou Anthropic, PBC], que processa os dados em [PREENCHER: Estados Unidos da América | região Europa (Espaço Econômico Europeu e Suíça)].
- **Forma:** envio eletrônico, por conexão criptografada, a cada mensagem recebida.
- **Finalidade:** só a classificação descrita acima.
- **Duração:** o provedor não usa os dados para treinar modelos e os guarda por no máximo [PREENCHER: "30 dias, para monitoramento de abuso" | "nenhum período: retenção zero contratada"].
- **Base e mecanismo:** a base legal é o legítimo interesse, e a transferência se apoia em [PREENCHER após decisão do advogado: "cláusulas-padrão contratuais aprovadas pela ANPD (Resolução CD/ANPD nº 19/2024, Anexo II), firmadas com o provedor" | "decisão de adequação da ANPD que reconhece o nível de proteção da União Europeia (Resolução CD/ANPD nº 32/2026)"].
- **Compartilhamento:** o provedor atua só como operador, sob nossas instruções, e não compartilha os dados com outros fins.
- **Responsabilidades e segurança:** o controlador acima responde pelo tratamento. Exigimos do provedor sigilo, criptografia em trânsito e exclusão no prazo.
- **Seus direitos:** você pode pedir **cópia integral das cláusulas** que regem a transferência, e vamos enviá-la em até 15 dias (Res. CD/ANPD nº 19/2024, Anexo I, art. 17, §1º). Você também pode exercer os direitos abaixo e peticionar à **Autoridade Nacional de Proteção de Dados (ANPD)**.

**Seus direitos** (LGPD, art. 18). Confirmar se tratamos seus dados, acessá-los, pedir a eliminação, pedir informações e **se opor** a este tratamento. Se você se opuser ou pedir a exclusão, apagamos tudo o que está associado ao seu número e paramos de processar suas mensagens. Basta escrever para [PREENCHER: e-mail do encarregado], de preferência informando o número de WhatsApp. Para confirmar que o número é seu, podemos pedir que você mande uma mensagem a partir dele. A confirmação simples é imediata. A resposta completa sai em até 15 dias (LGPD, art. 19). Você também pode reclamar à ANPD (gov.br/anpd).

*Atualizado em [PREENCHER: data] · versão [PREENCHER].*

**Recado do WhatsApp** (campo "Recado"/"Sobre"; limite de cerca de 139 caracteres [em aberto: confirmar no aparelho]):

> `Uso um assistente que lê as mensagens recebidas para organizar minha agenda. Privacidade: [LINK]`

Alternativa mais curta: `Mensagens recebidas podem ser lidas por um assistente de agenda. Saiba mais: [LINK]`

`[LINK]` = URL curta e estável para a âncora da seção acima, por exemplo `https://[PREENCHER: domínio]/consent/privacy-policy#assistant`.

Nota: deixar a visibilidade do recado em "Todos". O recado sozinho é uma transparência fraca, porque pouca gente lê. Cabe ao advogado decidir se basta, junto com a política (§7.6).

---

## 5. Especificação de retenção e exclusão (para implementar)

Base: retenção pela finalidade e eliminação ao fim (arts. 15 e 16) [norma, 10/11/2026]; direitos (arts. 18 e 19) [norma, 10/11/2026]. Os prazos de 90 dias e 12 meses são **provisórios até o advogado assinar**.

### 5.1 Inventário de armazenamento

| Armazenamento | Conteúdo pessoal | Chave do titular | Retenção | Ao vencer |
|---|---|---|---|---|
| Intake (mensagem bruta) | texto, ID WAHA, `recebido_em` | `remetente_hmac` | `expira_em = recebido_em + 90 dias` | DELETE físico |
| `ai_outputs` (kind=classification) | resultado da classificação; **sem texto** | via `intake_id` / `remetente_hmac` | igual ao intake (90 dias), salvo se estiver no conjunto de avaliação | DELETE |
| Conjunto de avaliação (cópia do texto selecionado + rótulos) | texto **mascarado** (sem nomes, CPF ou endereço visíveis), rótulo | `remetente_hmac` | `expira_em = min(fim_L4, criado_em + 12 meses)` | DELETE. Não "anonimizar" texto livre: ele pode identificar a pessoa |
| Eventos (`ai_feedback`, intake e transições de estado) | **nenhum conteúdo, nenhum número**: só ids, enums e datas | — | append-only, permanente | não precisa apagar. **Regra de construção:** evento nunca carrega texto nem HMAC |
| Lista de exclusão | `remetente_hmac`, motivo (enum: `dono`, `oposicao`, `pedido_exclusao`), data | HMAC | enquanto vigorar | remoção só por ação do dono |
| Log de leitura (quem leu, quando, qual item) | id do admin, ids de itens | — | [PREENCHER, sugestão de 6 meses] | DELETE |
| Registro de pedidos de titular | data, canal, direito pedido, status, contagem de linhas apagadas, prazo cumprido. **Sem número após a conclusão** | — | 5 anos (prova de cumprimento, art. 6, X) [recomendação] | DELETE |
| Logs da aplicação e do WAHA | **proibido** texto ou número | — | padrão da plataforma | — |
| Backups do Supabase | tudo acima | — | janela do plano [PREENCHER: dias] | expiram sozinhos; divulgado no aviso |
| Provedor de LLM | texto do prompt | — | ≤30 dias (OpenAI, abuso) ou zero com ZDR; Anthropic conforme DPA | auto. Usar `store=false` e não usar a Files API |

### 5.2 Regras de construção
1. **HMAC:** `HMAC-SHA256(chave_assistant, E.164 normalizado)`.
   - A chave fica no cofre de segredos do ambiente do assistant, nunca no banco.
   - Na rotação, guardar a lista de chaves anteriores (só ids) até a última linha criada com cada chave expirar, para que a exclusão por número continue achando tudo.
2. **Filtro antes de gravar** (seam do seed, item 4 do plano). Uma mensagem só é gravada se cumprir todas as condições:
   - não é `from_me`;
   - não veio da própria API;
   - é 1:1;
   - não é grupo, status nem transmissão;
   - não está na lista de exclusão;
   - tem `timestamp ≥ paired_at`;
   - o ID WAHA ainda não foi visto.

   Mídia sem texto não grava o conteúdo, só o desfecho `skipped`.
3. **Prompt ao LLM:** só o texto. Nunca número, nome do contato ou metadados de chat.
4. **Job de retenção** (diário):
   - apaga as linhas com `expira_em < now()` em todos os armazenamentos de 5.1;
   - emite o evento `retencao_executada{armazenamento, linhas_apagadas, executado_em}` (só contagens);
   - alerta se não houver execução bem-sucedida em 48 h. Sem silêncio: falha vira evento e alerta.
5. **Mascaramento ao entrar no conjunto de avaliação:** remover nomes próprios, números de documento, e-mails, telefones e endereços. Se o dono marcar "sensível" ou "menor" ao rotular, a linha sai do conjunto na hora (DELETE).

### 5.3 Exclusão e oposição por número (art. 18, IV e §2)
1. **Entrada:** pedido pelo canal do encarregado. Registrar `pedido_titular{id, recebido_em, canal, direito}`, sem conteúdo.
2. **Congelamento imediato:** ao receber o pedido, incluir o HMAC na lista de exclusão (motivo `pedido_exclusao` ou `oposicao`). Nada novo desse número entra a partir dali.
3. **Verificação de titularidade:** o titular manda uma mensagem a partir do número, ou responde a um código. Não pedir documento sem necessidade.
4. **Execução:** calcular o HMAC com a chave atual e com as anteriores. Apagar em intake, `ai_outputs` ligados, conjunto de avaliação e log de leitura dos itens. Endpoint admin-only: `DELETE /api/assistant/titulares/{numero}`. O número só trafega no corpo da requisição e nunca é gravado.
5. **Repasse** (art. 18 §6): o provedor de LLM não guarda por número. Registrar que a retenção dele é ≤30 dias ou zero. Os backups expiram na janela divulgada.
6. **Resposta ao titular:** confirmar a exclusão e a oposição. Se algo não puder ser feito na hora, dizer por quê (art. 18 §4, II).
7. **Fechamento:** o registro guarda só a contagem de linhas apagadas e as datas. O número sai do registro. O HMAC continua **só** na lista de exclusão enquanto a oposição valer.
8. **Teste de aceitação:** semear 3 números e pedir a exclusão de 1. Zero linhas desse HMAC fora da lista de exclusão. As linhas dos outros 2 ficam intactas. Uma nova mensagem do número excluído termina em `skipped_excluded`.

### 5.4 Prazos de resposta

| Pedido | Prazo legal | Prazo da casa | Fonte |
|---|---|---|---|
| Confirmação de existência / acesso em formato simplificado | imediatamente | no mesmo dia útil | art. 19, I [norma, 10/11/2026] |
| Declaração completa (origem, critérios, finalidade) | até 15 dias do requerimento | 15 dias corridos | art. 19, II [norma, 10/11/2026] |
| Eliminação / oposição | "nos prazos … previstos em regulamento" (ainda não editado); resposta quando não for imediata | congelamento no mesmo dia; execução em até 5 dias úteis; teto de 15 dias | art. 18 §§4–5 [norma, 10/11/2026]; regulamento da ANPD pendente [publicação profissional, 10/11/2026] |
| Cópia das cláusulas da transferência | 15 dias | 15 dias | Res. 19/2024, Anexo I, art. 17 §1 [norma, via KB em 05/11/2026] |
| Comunicação de incidente à ANPD e aos titulares | 3 dias úteis | 3 dias úteis | Res. 15/2024, art. 6 [norma, via KB em 05/11/2026] |

**Prazos em dobro de agente de pequeno porte: não aplicar.** O tratamento é de alto risco (Res. 2/2022 art. 3) [norma, via KB em 05/11/2026].

---

## 6. Termo de aceite de risco: Termos de Uso do WhatsApp

**TERMO DE CIÊNCIA E ACEITE DE RISCO: uso de cliente não oficial (WAHA) na linha pessoal de WhatsApp**

Eu, [PREENCHER: nome completo], CPF [PREENCHER], titular da conta de WhatsApp vinculada ao número [PREENCHER], agindo [PREENCHER: "em nome próprio" | "em nome próprio e como representante de <razão social>, CNPJ <…>"], declaro que:

1. **Conheço os Termos de Serviço do WhatsApp**, versão em vigor desde 04/01/2021 (lida em 10/11/2026 em whatsapp.com/legal/terms-of-service). Entre outras coisas, eles proíbem:
   - "gain or attempt to gain unauthorized access to our Services or systems";
   - "collect information of or about our users in any impermissible or unauthorized manner";
   - "reverse engineer … or extract code from our Services";
   - "create software or APIs that function substantially the same as our Services".

   Eles também permitem que o WhatsApp "modify, suspend, or terminate your access to or use of our Services anytime for any reason".
2. **Entendo que o WAHA é um cliente não oficial**, não autorizado pelo WhatsApp/Meta, e que conectá-lo à minha conta pode ser tratado como violação desses Termos.
3. **Entendo as consequências possíveis:**
   - suspensão temporária ou **banimento definitivo** da conta;
   - perda do uso do WhatsApp nesse número;
   - perda do histórico de conversas que não tiver backup;
   - perda de grupos e contatos dependentes da conta;
   - nenhum direito a recurso ou indenização garantido. Os Termos elegem a lei e o foro da Califórnia, e a aplicação do direito do consumidor brasileiro é incerta [em aberto].
4. **Entendo que o modo só-leitura NÃO elimina o risco.** Não enviar mensagens, não marcar como lidas e não aparecer online reduz sinais de automação, mas a conexão do cliente não oficial já pode ser detectada.
5. **Entendo que o risco é meu, como pessoa.** A conta é pessoal. Uma eventual suspensão me afeta diretamente, e nenhuma empresa da qual eu seja sócio me indeniza por isso.
6. **Antes do pareamento**, comprometo-me a:
   - (a) fazer backup das conversas;
   - (b) concluir antes a prova em número descartável (24 h sem presença, "visto" ou envio);
   - (c) saber desconectar o aparelho a qualquer momento em *WhatsApp > Dispositivos conectados*.
7. Ao meu conhecimento, a conduta **não é crime**: conta própria, ninguém interceptado, e eu sou parte das conversas [doutrina; confirmar com advogado: CP art. 154-A; Lei 9.296/96; STF RE 583.937, Tema 237, citação não verificada hoje]. O risco descrito aqui é **contratual**.
8. Este aceite **não substitui** as obrigações da LGPD perante os interlocutores (teste de legítimo interesse, aviso, retenção, direitos), que seguem valendo.
9. Posso revogar este aceite a qualquer momento desconectando o aparelho. A revogação dispara a parada da ingestão.

[PREENCHER: cidade], [PREENCHER: data]. Assinatura: ______________________ (assinatura eletrônica avançada basta para prova entre as partes).

---

## 7. Pendências que exigem advogado (OAB) ou encarregado

| # | Pendência | Quem | Bloqueia o pareamento da linha pessoal? |
|---|---|---|---|
| 1 | **Quem é o controlador:** NoctusAI com CNPJ ou o dono como empresário. Hoje `consent.ts` declara pessoa física como controlador e como encarregado. Alinhar a política inteira | Advogado + dono | Sim |
| 2 | Leitura do art. 4, I (fora da exceção de uso pessoal). Sem orientação da ANPD | Advogado | Sim |
| 3 | Assinar o teste de legítimo interesse (§1), sobretudo o balanceamento da expectativa do interlocutor (R4) | Advogado + controlador + encarregado | Sim |
| 4 | **Mecanismo de transferência por provedor:** (a) cláusulas-padrão da ANPD (Anexo II, adotadas "na íntegra e sem alteração", art. 16) negociadas com OpenAI/Anthropic; ou (b) região UE da OpenAI + Res. 32/2026 (confirmar texto e alcance no DOU; exige aprovação da OpenAI); ou (c) evitar a transferência. Os DPAs atuais usam as SCCs da UE: atendem à norma brasileira? O prazo de adaptação de 12 meses venceu por volta de 23/08/2025 | Advogado | Sim |
| 5 | Tratamento de dados sensíveis incidentais: basta a regra "exclusão + retirada do conjunto"? Adotar o `sensivel_suspeito` automático (R2)? | Advogado | Sim |
| 6 | Texto final do aviso de privacidade (§4) e se o recado basta como transparência (art. 10 §2) | Advogado | Sim |
| 7 | Prazos de retenção (90 dias, 12 meses, log de leitura, registro de pedidos de 5 anos) | Advogado | Sim |
| 8 | **Ato formal de nomeação do encarregado** (Res. 18/2024, art. 3), substituto (art. 4) e o conflito de interesses de quem decide e é encarregado ao mesmo tempo (art. 19 §1, II) | Advogado + dono | Recomendado antes |
| 9 | RIPD (§3): parecer e aceite do risco residual | Encarregado + controlador | Sim |
| 10 | Entrada no ROPA (§2): validar e arquivar | Encarregado | Sim |
| 11 | Canal do titular operante e procedimento de §5.3 testado | Encarregado | Sim |
| 12 | Enquadramento como agente de pequeno porte: registrar que **não** se aplica a este tratamento (alto risco) | Advogado | Não |
| 13 | Confirmar a citação do STF RE 583.937 (Tema 237) e a ausência de crime | Advogado | Não (o aceite do §6 cita como "a confirmar") |
| 14 | Termo de aceite (§6) assinado pelo dono | Dono | Sim |
| 15 | Contratar ZDR ou confirmar por escrito a retenção do provedor; arquivar os DPAs vigentes | Dono + advogado | Sim (junto com o item 4) |
| 16 | Acompanhar o regulamento de direitos dos titulares da ANPD (prazos em §5.4) e qualquer norma de IA | Encarregado | Não |

**Não precisa de advogado:** S1 a S4 e a prova na linha descartável. Ali só há dados do próprio dono, ou nenhum dado de terceiro, se o número descartável não receber mensagens de outras pessoas.

---

## Mudanças propostas (para o tech-lead; nada foi editado)
- **KB `PATTERNS/legal/lgpd-privacy-program.md`:**
  - §2: incluir a linha "assistant: controlador NoctusAI, legítimo interesse, LLM nos EUA ou UE".
  - §9: na matriz de provedores, registrar a região UE da OpenAI e a Res. 32/2026.
  - §18: trocar "Res. 32/2026, unverified, do not rely" por "confirmada por várias publicações profissionais; texto do DOU a ler".
- **Relatório `research/lgpd-personal-line.md` §4:** corrigir a citação dos Termos do WhatsApp (ver §0.3).
- **Código (S2/S3):** cumprir §5.2 e §5.3 (HMAC com chaves rotacionáveis, eventos sem conteúdo nem HMAC, job de retenção com alerta, endpoint de exclusão, `store=false`).

## Fontes (lidas na data indicada)
- LGPD, Planalto (arts. 6 III, 7 IX, 10, 11 §1, 16, 18, 19, 37, 38, 41 §1), 10/11/2026 [norma]: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- Res. CD/ANPD 19/2024, DOU (Res. art. 1, parágrafo único; Anexo I arts. 9, 16, 17), via KB em 05/11/2026; a página não abriu em 10/11/2026 [norma]: https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-19-de-23-de-agosto-de-2024-580095396
- Res. CD/ANPD 2/2022, 15/2024 e 18/2024, via KB `lgpd-privacy-program.md` §17, 05/11/2026 [norma]
- ANPD, Guia de Legítimo Interesse (fev/2024) e perguntas e respostas sobre RIPD, via KB em 05/11/2026 [órgão oficial]
- Res. CD/ANPD 32/2026 (adequação da UE), 10/11/2026 [publicação profissional]: [Lefosse](https://lefosse.com/noticias/alerta/transferencia-internacional-de-dados-pessoais-anpd-anuncia-decisao-de-adequacao-mutua-entre-brasil-e-uniao-europeia/) · [Mattos Filho](https://www.mattosfilho.com.br/unico/brasil-ue-protecao-dados-equivalentes/) · [Cescon Barrieu](https://cesconbarrieu.com.br/decisao-de-adequacao-reciproca-entre-brasil-e-uniao-europeia-implicacoes-para-fluxos-transfronteiricos-de-dados/) · [Legismap](https://legismap.com.br/leis-e-normas/resolucao-anpd-n-032-de-26-01-2026)
- Regulamento de direitos dos titulares (pendente), 10/11/2026 [publicação profissional]: [Legismap](https://legismap.com.br/conteudos/artigos-e-noticias/anpd-abre-tomada-de-subsidios-para-norma-de-direitos-dos-titulares-de-dados-pessoais) · [Demarest](https://www.demarest.com.br/anpd-publica-relatorio-de-execucao-da-agenda-regulatoria-2025-2026/)
- OpenAI, "Your data" (retenção de 30 dias, sem treino, ZDR, região UE), 10/11/2026: https://developers.openai.com/api/docs/guides/your-data
- Anthropic, "API and data retention" e privacy center (ZDR, sem treino), 10/11/2026: https://platform.claude.com/docs/en/manage-claude/api-and-data-retention · https://privacy.claude.com/en/articles/8956058-i-have-a-zero-data-retention-agreement-with-anthropic-what-products-does-it-apply-to
- Termos de Serviço do WhatsApp (vigentes desde 04/01/2021), 10/11/2026: https://www.whatsapp.com/legal/terms-of-service
- Arquivos do projeto lidos (somente leitura):
  - `/Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/worktrees/ac-d46-plan/project-history/assistant-chatbot/research/lgpd-personal-line.md`
  - `/Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/worktrees/ac-d46-plan/project-history/assistant-chatbot/phase0-d46-shadow-line.md` §6
  - `/Users/rapha/Documents/repository/NoctusAI/noctusai/KNOWLEDGE-BASE/CONTEXT/PATTERNS/legal/lgpd-privacy-program.md`
  - `/Users/rapha/Documents/repository/NoctusAI/noctusai/seed/framework/frontend/src/content/consent.ts`
