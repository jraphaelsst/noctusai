# Planejamento da jornada comercial e operacional da One Consultoria Imobiliária

**Documento de continuidade --- versão de consolidação**\
**Data:** 26 de novembro de 2026\
**Escopo:** da entrada do lead até a conclusão das responsabilidades do
Jurídico no processo de venda.\
**Fora do escopo desta versão:** desenho, gatilhos e automações de
pós-venda.

------------------------------------------------------------------------

## 1. Objetivo deste documento

Consolidar em um único arquivo Markdown o planejamento construído para a
jornada do cliente e o processo de venda da One Consultoria Imobiliária,
preservando:

-   decisões já tomadas;
-   funcionamento atual identificado no código;
-   distinções conceituais importantes;
-   responsabilidades operacionais conhecidas;
-   regras e restrições para futuras automações;
-   pontos ainda não definidos;
-   sugestões, recomendações e próximos passos.

Este documento é uma base de transferência de contexto para outro
ambiente de trabalho. Não representa autorização para alterar o
repositório, implementar funcionalidades ou modificar prompts.

## 2. Limites e princípios de trabalho

1.  **Planejamento, não implementação.** Nesta etapa, não alterar
    código, banco de dados, migrations, prompts, configurações ou
    documentação do repositório.
2.  **Preservar o que existe.** Antes de sugerir uma mudança,
    identificar a implementação atual e evitar duplicar módulos,
    entidades, telas ou fluxos.
3.  **Separar fato de hipótese.** Distinguir o que foi confirmado no
    código, o que foi definido pelo usuário e o que ainda é sugestão.
4.  **Não antecipar o pós-venda.** O escopo atual termina quando o
    Jurídico conclui sua parte no processo de venda. O pós-venda será
    tratado em uma etapa posterior.
5.  **Não misturar jornada, processo e automação.** São conceitos
    relacionados, mas não equivalentes.
6.  **Manter histórico e rastreabilidade.** Mudanças de etapa, recusas,
    reagendamentos, documentos e eventos não devem apagar o histórico
    anterior.
7.  **Automação sob controle.** Cada etapa e automação deverá poder ser
    habilitada ou desabilitada independentemente, conforme configuração
    da empresa.
8.  **Não atribuir autonomia indevida à IA.** Julia não deve inventar
    informações, confirmar eventos sem evidência ou tomar decisões que
    pertencem a pessoas responsáveis.

------------------------------------------------------------------------

## 3. Vocabulário e modelo conceitual

### 3.1 Jornada do cliente

É o histórico completo do relacionamento entre a pessoa e a One,
incluindo contatos, atendimentos, oportunidades, transações, documentos,
visitas e interações ao longo do tempo.

Uma pessoa pode voltar a se relacionar com a imobiliária e participar de
mais de uma transação. Portanto, a jornada não deve ser confundida com
uma única venda.

### 3.2 Processo ou transação

É uma operação específica, como uma compra ou venda. Uma mesma pessoa
pode ter diversos processos ao longo do relacionamento.

Os papéis devem ser registrados **por transação**, não como uma
característica global e imutável da pessoa. Uma pessoa pode ser
compradora em uma operação e vendedora em outra; também pode assumir
mais de um papel em uma transação, conforme o caso.

### 3.3 Atendimento e oportunidade

No modelo atual do Social Wiring, o cartão do funil é um `atendimento`.
A negociação é uma etapa do ciclo desse atendimento, não uma entidade
que substitui o atendimento.

A oportunidade comercial se torna concreta quando existe intenção de
visita acompanhada de disponibilidade candidata. Interesse genérico em
comprar ou vender, isoladamente, não deve gerar automaticamente uma
oportunidade de visita.

### 3.4 Automação

É uma ação executada por Julia ou por outro mecanismo em uma etapa ou
momento definido. A automação não é a jornada nem o processo; ela atua
sobre eles e deve deixar registro auditável.

------------------------------------------------------------------------

## 4. Jornada operacional considerada neste planejamento

O fluxo de alto nível, limitado ao trabalho até o Jurídico, é:

1.  Entrada do lead.
2.  Primeiro contato e qualificação inicial por Julia.
3.  Análise da qualificação e supervisão.
4.  Validação por Rapha e encaminhamento ao corretor escolhido.
5.  Atendimento comercial pelo corretor.
6.  Busca e seleção de imóvel, visitas, proposta e negociação.
7.  Aceite da proposta.
8.  Abertura do Processo de Venda no ERP.
9.  Execução do processo de venda, incluindo as atividades do Jurídico.
10. Conclusão da responsabilidade do Jurídico no processo de venda.

**O pós-venda não está sendo desenhado nesta versão.** Não definir aqui
seus gatilhos, cadências, mensagens ou automações. A transição para
pós-venda deverá ser retomada em um planejamento separado, depois que o
fluxo anterior estiver fechado.

------------------------------------------------------------------------

## 5. Responsabilidades e limites operacionais conhecidos

### 5.1 Julia --- SDR e qualificação inicial

O escopo atual da Julia é a qualificação inicial do lead, até a
identificação de intenção de visita.

Julia atualmente:

-   realiza o primeiro contato;
-   coleta informações iniciais;
-   identifica o interesse e o contexto do lead;
-   busca informações necessárias para avaliar a aderência;
-   quando há intenção concreta de visita, solicita duas opções
    possíveis de data e horário;
-   encaminha o material para avaliação e decisão humana.

Julia **não agenda nem confirma a visita** no fluxo atual. Ela coleta
duas opções de disponibilidade e encaminha a Rapha. A confirmação e a
organização efetiva da visita ficam para a operação humana.

O SDR da Julia está definido e próximo de ficar pronto. Não reconstruir,
reescrever ou modificar esse SDR neste planejamento.

### 5.2 Dados coletados

No primeiro contato, os dados básicos previstos são:

-   nome;
-   telefone;
-   e-mail.

CPF e RG só devem ser solicitados quando o lead demonstrar intenção
concreta de visita e fornecer opções de disponibilidade. Essa coleta
adicional se refere ao cliente principal, não aos acompanhantes.

A coleta deve respeitar necessidade, finalidade, acesso restrito e
princípios da LGPD.

### 5.3 Supervisão da qualificação

Julia realiza sua própria análise do lead. A intenção não é fazer Rapha
analisar manualmente cada conversa desde o início, mas permitir que ele
revise o resultado estruturado da análise.

A análise deve apresentar cinco dimensões:

1.  **Qualificação:** o quanto o lead foi efetivamente qualificado.
2.  **Completude:** se as informações necessárias foram obtidas.
3.  **Aderência:** compatibilidade do lead com o perfil e os critérios
    comerciais.
4.  **Eficiência:** qualidade e eficiência da condução do atendimento.
5.  **Conversão:** sinais e probabilidade de avanço, com justificativas.

A análise deve trazer evidências, trechos relevantes da conversa e uma
recomendação de próxima ação. Não basta apresentar uma nota sem
justificativa.

Rapha valida a análise como **OK** ou **não OK**. Essa validação é
distinta da escolha do corretor e do encaminhamento do lead.

Se a análise não estiver adequada, deve ser possível solicitar revisão
ou nova análise, preservando a versão anterior e o histórico da revisão.
Julia não deve retomar ou executar ações automaticamente após uma
reprovação, a menos que exista uma regra explícita configurada para
isso.

### 5.4 Encaminhamento ao corretor

O fluxo atual conhecido é:

1.  leads qualificados chegam a Rapha;
2.  Rapha revisa e valida a análise da Julia;
3.  Rapha escolhe o corretor;
4.  Rapha encaminha o lead ao corretor escolhido.

Não há, no fluxo atual descrito, distribuição automática para uma fila
de corretores ou atribuição automática por algoritmo. Não projetar essa
automação como se já existisse.

### 5.5 Corretor

Depois do encaminhamento, o corretor assume a condução comercial humana,
incluindo:

-   contato comercial;
-   entendimento mais aprofundado da necessidade;
-   seleção e apresentação de imóveis;
-   organização e confirmação de visitas;
-   realização e acompanhamento das visitas;
-   proposta;
-   negociação;
-   condução até o aceite ou encerramento da oportunidade.

O corretor não é atualmente o responsável pelo acompanhamento
operacional posterior à transferência formal para o Jurídico. Preservar
essa divisão até que exista uma decisão diferente.

### 5.6 Jurídico

Após o aceite da proposta, o Jurídico assume o acompanhamento
operacional das etapas jurídicas e de fechamento que lhe cabem,
incluindo preparação, análise, revisão e assinatura contratual e demais
providências pertinentes ao processo.

O Jurídico permanece responsável pelo acompanhamento até a conclusão de
sua parte no processo de venda, respeitando as responsabilidades
específicas de outros participantes quando existirem.

Não atribuir ao Jurídico uma confirmação de entrega de chaves ou outro
marco posterior sem validar que isso faz parte do procedimento real da
One. Essa questão pertence ao futuro desenho do pós-venda e está fora do
escopo atual.

------------------------------------------------------------------------

## 6. Funil comercial: comportamento e decisões

### 6.1 O cartão continua sendo um Atendimento

O modelo documentado no código registra que o cartão deve permanecer
como `atendimento` durante seu ciclo de vida. "Negociação" é uma etapa,
não uma nova entidade que substitui o atendimento.

### 6.2 Sequência de etapas identificada

A migration `034_pipeline_funil_processos.sql` e a migration de
transição `060_negociacoes_venda_to_atendimentos.sql` documentam o funil
comercial e sua evolução.

A sequência conceitual identificada inclui:

1.  `qualificacao`;
2.  `visitas`;
3.  `proposta_recebida`;
4.  `negociacao`;
5.  `proposta_decisao`.

A etapa de decisão utiliza papéis de etapa, incluindo o comportamento de
proposta aceita. Quando a proposta é aceita, o atendimento deixa o Funil
e dá origem a um Processo de Venda. Quando a proposta é rejeitada, o
atendimento permanece no histórico do funil na etapa de decisão, sem
apagar o registro.

A lista acima descreve o fluxo identificado nas migrations consultadas;
a configuração efetiva das etapas deve ser conferida no ambiente de
execução antes de qualquer implementação.

### 6.3 Agendamentos e visitas

A migration `061_atendimento_agendamentos.sql` estabelece agendamentos
como registros independentes associados a um `atendimento`, permitindo
múltiplos agendamentos para o mesmo atendimento.

Os tipos identificados incluem visita, ligação, reunião e outro. O
modelo consultado inclui data/hora, tipo, nota e antecedência de
lembrete.

Pontos relevantes:

-   cada agendamento deve ser preservado como evento próprio;
-   reagendamentos não devem apagar a tentativa anterior;
-   visita solicitada não é o mesmo que visita confirmada;
-   visita confirmada não é o mesmo que visita realizada;
-   faltas e cancelamentos devem permanecer rastreáveis.

O modelo consultado não demonstrou, por si só, um fluxo completo de
status e responsável para cada agendamento. Não presumir funcionalidades
que não foram verificadas.

### 6.4 Reagendamento

Reagendamento deve ser tratado de forma rastreável e, no desenho do
fluxo, como uma condição/etapa operacional própria quando isso fizer
sentido para a experiência do usuário. O histórico da visita anterior
deve permanecer.

------------------------------------------------------------------------

## 7. Imóveis e histórico da oportunidade

### 7.1 Vários imóveis candidatos

Uma oportunidade pode envolver vários imóveis candidatos durante a
busca. Quando o cliente escolhe um imóvel e decide avançar com uma
proposta, esse imóvel passa a ser o imóvel principal da operação.

Os demais imóveis avaliados não devem ser apagados. Devem permanecer no
histórico como alternativas consideradas.

### 7.2 Imóvel indisponível ou inativo

Se o imóvel associado à oportunidade se tornar inativo, indisponível ou
deixar de fazer parte do catálogo:

-   não apagar o histórico da oportunidade;
-   não realizar uma movimentação silenciosa;
-   retornar a oportunidade à etapa apropriada de busca/seleção de
    imóvel, se essa for a decisão operacional correta;
-   registrar o motivo e o momento da alteração;
-   notificar o responsável;
-   exigir ciência/acknowledgement da pessoa responsável quando a
    mudança exigir ação humana.

A notificação inicialmente prevista é para Rapha. No futuro, o
roteamento poderá considerar corretor responsável e hierarquia de
gestão, mas isso não deve ser tratado como comportamento atual.

A notificação deve conter, no mínimo:

-   imóvel afetado;
-   motivo da indisponibilidade;
-   lead/oportunidade afetada;
-   etapa anterior;
-   etapa atual;
-   ação esperada.

### 7.3 Imóveis no catálogo versus identidade histórica

A migration `063_imovel_registry.sql` distingue:

-   `imoveis`: espelho/cache do catálogo Vista, que pode encolher quando
    um imóvel é vendido ou retirado;
-   `imovel_registry`: registro histórico de identidade, com
    comportamento de preservação e snapshots de informações conhecidas.

Para histórico de processos, não tratar o espelho volátil do catálogo
como fonte histórica permanente. A identidade e os dados históricos
devem ser preservados pelo registro apropriado.

------------------------------------------------------------------------

## 8. Aceite da proposta e abertura do Processo de Venda

O aceite da proposta é a transição entre a fase comercial e a execução
do fechamento.

A distinção funcional é:

-   **Funil:** responde se a oportunidade comercial vai avançar para um
    fechamento.
-   **Processo de Venda:** acompanha a execução do fechamento depois do
    aceite.

A migration `041_processos_venda.sql` documenta a criação do processo
após o aceite, com idempotência baseada no identificador da negociação
de venda. O serviço consultado também indica que não existe criação
livre de processo sem a origem comercial esperada: o processo nasce do
aceite.

O processo deve manter vínculo com cliente, negociação/proposta,
corretor e informações relevantes da operação.

### 8.1 Etapas do Processo de Venda

A implementação consultada teve uma evolução importante:

-   a migration inicial registra oito etapas padrão;
-   a tela e o serviço atuais indicam que as etapas são representadas
    por registros configuráveis no banco;
-   a interface `ProcessosVenda.tsx` permite configurar etapas;
-   o enum legado é mantido como compatibilidade/rollback, enquanto
    `etapa_id` é a referência autoritativa no modelo evoluído.

As oito etapas iniciais identificadas são:

1.  `elaboracao_contrato`;
2.  `analise_partes`;
3.  `revisao_contrato`;
4.  `assinatura`;
5.  `financiamento_escritura`;
6.  `finalizacao`;
7.  `entrega_chaves`;
8.  `nota_fiscal`.

Essas etapas devem ser entendidas como a configuração inicial/default
identificada, não como uma lista imutável. A configuração efetiva do
ambiente deve ser verificada antes de especificar mudanças.

A tela descreve o Processo de Venda como execução pós-aceite da
proposta, do contrato à nota fiscal.

------------------------------------------------------------------------

## 9. Contratos e assinaturas: funcionalidades existentes identificadas

Há estruturas de contratos tanto no ERP imobiliário quanto no Social
Wiring. Não assumir que são uma única fonte de verdade ou que estão
sincronizadas sem verificar a integração.

### 9.1 ERP --- módulo de Contratos

A página `products/erp-imobiliario/frontend/src/pages/Contratos.tsx`
apresenta um módulo próprio de contratos, com cadastro, filtros, status,
resumo e visualização de detalhes.

Os campos identificados incluem tipo, cliente, imóvel, proposta, valor
total, entrada, parcelas, datas, data de assinatura e observações.

A rota e a página já existem. Não propor a criação de outro módulo de
contratos no ERP.

### 9.2 Social Wiring --- contratos vinculados ao Atendimento

A migration `106_atendimento_contratos.sql` estabelece contratos
vinculados ao atendimento, permitindo mais de um contrato para um mesmo
atendimento, por exemplo contrato principal e instrumento relacionado a
permuta.

Os status identificados incluem:

-   `rascunho`;
-   `em_revisao`;
-   `enviado_assinatura`;
-   `assinado`;
-   `cancelado`.

As versões dos documentos são imutáveis: cada novo upload gera uma nova
versão, preservando o histórico. O modelo também prevê cuidados de LGPD,
acesso e exclusão lógica.

### 9.3 Assinatura eletrônica

A migration `134_contrato_assinatura.sql` documenta envelopes de
assinatura vinculados a um contrato e a uma versão específica.

Os status identificados incluem:

-   `pendente`;
-   `parcial`;
-   `concluido`;
-   `cancelado`;
-   `expirado`.

O modelo registra provedor, identificador externo, link de assinatura,
signatários, datas de envio/conclusão e versão assinada. O PDF assinado
é registrado como uma nova versão do contrato, com origem `assinado`.

Esse desenho é mais robusto do que simplesmente alterar um campo de
status para "assinado". Deve-se preservar a relação entre contrato,
versão enviada, envelope e documento final assinado.

### 9.4 Ponto de integração em aberto

É necessário esclarecer como o módulo de contratos do ERP e os contratos
do Social Wiring se relacionam:

-   qual sistema cria o registro inicial;
-   qual sistema é a fonte de verdade do contrato;
-   como versões e status são sincronizados;
-   como o envelope de assinatura é iniciado e atualizado;
-   como o documento assinado retorna ao processo;
-   como evitar registros duplicados ou divergentes.

Não assumir integração automática apenas porque os dois produtos possuem
funcionalidades de contrato.

------------------------------------------------------------------------

## 10. Controle de chaves: distinção importante

A página `products/erp-imobiliario/frontend/src/pages/Chaves.tsx`
implementa controle de custódia física de chaves de imóveis.

As funcionalidades identificadas incluem:

-   cadastro de chave vinculada a imóvel;
-   código, descrição e observações;
-   status como disponível, emprestada e perdida;
-   registro de retirada e devolução;
-   histórico e identificação de quem retirou/devolveu.

**Isso não comprova, por si só, a entrega formal das chaves ao
comprador.**

Controle interno de chaves e confirmação de posse/entrega ao cliente são
eventos diferentes. Não utilizar o módulo de custódia como prova
automática de entrega ao comprador.

A confirmação formal de entrega não foi definida nesta etapa e não deve
ser transformada em requisito de pós-venda agora.

------------------------------------------------------------------------

## 11. Linha do tempo e auditoria

O serviço
`products/social-wiring/backend/app/modules/card_hub/timeline_service.py`
já consolida eventos relacionados a pessoas/clientes, atendimentos e
processos de venda.

Foram identificados eventos de interação, movimentação, visita e
sistema. A linha do tempo deve ser aproveitada como base existente, em
vez de criar uma segunda timeline paralela sem necessidade.

Um detalhe importante no serviço consultado: `ocorrido_em` representa o
horário real do evento, e não simplesmente o `created_at` do registro.
Essa distinção deve ser preservada ao ordenar e exibir eventos.

Requisitos transversais recomendados:

-   eventos com data/hora real;
-   origem identificável;
-   histórico de alterações;
-   idempotência para evitar duplicidade;
-   ordenação consistente;
-   evidência do evento que justificou uma transição;
-   trilha de auditoria para ações humanas e automatizadas.

------------------------------------------------------------------------

## 12. Regras para automações futuras dentro do escopo atual

Estas são diretrizes de planejamento, não implementação aprovada.

### 12.1 Configuração independente

Cada etapa da atuação da Julia e cada automação devem poder ser
habilitadas/desabilitadas de forma independente por empresa.

Desabilitar uma automação deve impedir novas execuções conforme a regra
definida, sem apagar o histórico já produzido. O comportamento de
execuções já enfileiradas ou em andamento precisa ser especificado antes
da implementação.

### 12.2 Idempotência e duplicidade

Eventos que disparam automações devem ter identificadores e regras de
idempotência. Reprocessamentos, webhooks repetidos ou atualizações
duplicadas não podem gerar mensagens, processos ou tarefas duplicados.

### 12.3 Evidência e fonte do evento

Julia não deve afirmar que uma proposta foi aceita, contrato assinado ou
etapa jurídica concluída sem uma fonte de dados confiável.

Eventos críticos devem vir do sistema responsável ou de uma confirmação
humana autorizada, com autoria e timestamp.

### 12.4 Falhas e tentativas

O desenho futuro deve prever:

-   registro de tentativas;
-   falha e motivo;
-   política de retentativa;
-   limite de tentativas;
-   escalonamento para pessoa responsável;
-   prevenção de mensagens duplicadas;
-   visibilidade operacional do que ficou pendente.

### 12.5 Contato com o cliente

Toda automação de contato deve respeitar consentimento, finalidade,
horários permitidos e preferências de comunicação, além das regras
aplicáveis da LGPD.

### 12.6 Dados e permissões

Dados pessoais, documentos, informações financeiras e documentos
contratuais devem obedecer a permissões por função e necessidade de
acesso. Agentes de IA só devem receber os dados necessários à tarefa.

------------------------------------------------------------------------

## 13. Arquitetura e responsabilidades entre produtos

A orientação conceitual discutida é:

-   **Social Wiring:** fonte operacional dos atendimentos, status e
    eventos do relacionamento, além de atuar como emissor de eventos
    conforme a arquitetura existente.
-   **Agents:** configuração de agentes, permissões, regras,
    orquestração e execução das automações.
-   **ERP/CRM imobiliário da NoctusAI:** gestão de clientes,
    oportunidades, imóveis, processos e transações de negócio,
    respeitando o que já está implementado.

Essa é uma orientação arquitetural de planejamento. Antes de fechar
contratos de integração, é necessário verificar os limites reais entre
bancos, APIs, serviços e responsabilidades de cada produto.

Não duplicar entidades ou fontes de verdade sem uma justificativa
explícita.

------------------------------------------------------------------------

## 14. Processo de acesso e leitura do repositório --- documentação metodológica futura

Esta seção registra o aprendizado do processo de inspeção do código.
**Não é um arquivo de instruções a ser colocado na raiz do repositório,
nem um requisito para que outros agentes acessem o projeto.** É
documentação do método utilizado para investigar e compreender o
projeto, a ser reaproveitada quando fizer sentido.

### 14.1 Repositório inspecionado

-   Repositório: `jraphaelsst/noctusai`
-   Branch consultada: `dev`
-   URL: https://github.com/jraphaelsst/noctusai

### 14.2 Método que funcionou

1.  Consultar os metadados do repositório para confirmar nome e branch.
2.  Listar o conteúdo da raiz pela API de conteúdo do GitHub.
3.  Consultar diretórios reais e/ou recuperar a árvore Git recursiva
    para descobrir caminhos.
4.  Abrir os arquivos pelos caminhos exatos identificados.
5.  Quando apropriado, recuperar o conteúdo raw do arquivo na branch
    confirmada.
6.  Ler migrations, serviços, routers, páginas e navegação em conjunto
    para compreender o comportamento real.
7.  Registrar o caminho de cada arquivo consultado e separar evidência
    de interpretação.

Endpoints utilizados:

-   Metadados: `https://api.github.com/repos/jraphaelsst/noctusai`
-   Conteúdo da raiz:
    `https://api.github.com/repos/jraphaelsst/noctusai/contents?ref=dev`
-   Árvore recursiva:
    `https://api.github.com/repos/jraphaelsst/noctusai/git/trees/{SHA}?recursive=1`
-   Arquivo raw:
    `https://raw.githubusercontent.com/jraphaelsst/noctusai/dev/{CAMINHO}`

O SHA deve ser obtido da resposta da API, nunca presumido.

### 14.3 Aprendizado sobre falhas

Uma busca de código sem resultados ou um 404 em um caminho presumido não
demonstra que o repositório está inacessível. Neste caso, o problema foi
a utilização de caminhos incorretos e de uma estratégia de busca
inadequada, não uma falta de permissão do usuário.

A investigação deve localizar primeiro os caminhos reais e só depois
tentar abrir os arquivos. Se uma operação falhar, registrar qual
operação falhou, sem generalizar a falha para todo o acesso ao
repositório.

### 14.4 Arquivos efetivamente consultados nesta investigação

**Social Wiring** -
`products/social-wiring/frontend/src/nav/navGroups.ts` -
`products/social-wiring/backend/migrations/034_pipeline_funil_processos.sql` -
`products/social-wiring/backend/migrations/060_negociacoes_venda_to_atendimentos.sql` -
`products/social-wiring/backend/migrations/061_atendimento_agendamentos.sql` -
`products/social-wiring/backend/migrations/063_imovel_registry.sql` -
`products/social-wiring/backend/migrations/077_atendimento_negociacao.sql` -
`products/social-wiring/backend/migrations/106_atendimento_contratos.sql` -
`products/social-wiring/backend/migrations/134_contrato_assinatura.sql` -
`products/social-wiring/backend/app/modules/card_hub/timeline_service.py`

**ERP imobiliário** -
`products/erp-imobiliario/backend/migrations/041_processos_venda.sql` -
`products/erp-imobiliario/backend/app/services/processos_venda_service.py` -
`products/erp-imobiliario/backend/app/routers/processos_venda.py` -
`products/erp-imobiliario/frontend/src/pages/ProcessosVenda.tsx` -
`products/erp-imobiliario/frontend/src/pages/Chaves.tsx` -
`products/erp-imobiliario/frontend/src/pages/Contratos.tsx` -
`products/erp-imobiliario/frontend/src/App.tsx`

A lista acima registra os arquivos consultados na investigação, não uma
auditoria completa do repositório.

------------------------------------------------------------------------

## 15. Decisões consolidadas

  ---------------------------------------------------------------------
  Tema                               Decisão ou entendimento atual
  ---------------------------------- ----------------------------------
  Escopo desta rodada                Da entrada do lead até a conclusão
                                     da atuação do Jurídico no processo
                                     de venda

  Pós-venda                          Adiado para planejamento
                                     posterior; não desenhar agora

  Julia                              SDR e qualificação inicial até
                                     intenção de visita

  Agendamento                        Julia coleta duas opções; não
                                     confirma nem agenda a visita
                                     atualmente

  Dados iniciais                     Nome, telefone e e-mail

  CPF/RG                             Solicitar somente com intenção
                                     concreta de visita e
                                     disponibilidade candidata; apenas
                                     do cliente principal

  Supervisão                         Julia analisa; Rapha valida OK/não
                                     OK

  Encaminhamento                     Rapha escolhe e encaminha ao
                                     corretor

  Distribuição automática            Não é comportamento atual
                                     confirmado

  Atendimento                        O cartão permanece Atendimento;
                                     negociação é etapa

  Proposta aceita                    Sai do Funil e origina Processo de
                                     Venda

  Proposta rejeitada                 Preservar no histórico; não apagar
                                     atendimento

  Processo de Venda                  Execução pós-aceite, com etapas
                                     configuráveis na implementação
                                     evoluída

  Contratos                          Existem módulos/estruturas no ERP
                                     e no Social Wiring; integração e
                                     fonte de verdade precisam ser
                                     esclarecidas

  Controle de chaves                 Custódia interna não equivale à
                                     entrega formal ao comprador

  Timeline                           Aproveitar a timeline unificada
                                     existente

  Repositório                        Não alterar código nem documentos
                                     nesta etapa

  Documento metodológico             Registrar o método de inspeção do
                                     repositório aqui para documentação
                                     futura, sem colocá-lo na raiz do
                                     projeto
  ---------------------------------------------------------------------

------------------------------------------------------------------------

## 16. Pontos em aberto e perguntas para a próxima etapa

Estes pontos ainda precisam de validação antes de transformar o
planejamento em especificação funcional.

### 16.1 Processo comercial

-   Quais são exatamente os critérios objetivos para considerar um lead
    qualificado?
-   Quais campos são obrigatórios para a análise da Julia em cada tipo
    de lead?
-   Quais são os critérios de aprovação/reprovação da análise por Rapha?
-   Como registrar formalmente o encaminhamento ao corretor e a
    aceitação da responsabilidade por ele?
-   Quais estados e resultados devem existir para visita solicitada,
    confirmada, realizada, cancelada, reagendada e não comparecimento?

### 16.2 Proposta e transição para o Jurídico

-   Qual evento ou ação registra formalmente o aceite da proposta?
-   Quem tem permissão para confirmar o aceite?
-   Quais dados e documentos precisam estar completos para abrir o
    Processo de Venda?
-   Como o Jurídico recebe a responsabilidade e como essa transferência
    fica registrada?
-   Qual é o marco formal que indica que a responsabilidade do Jurídico
    foi concluída?
-   Quais atividades do processo são responsabilidade do Jurídico e
    quais dependem de terceiros?

### 16.3 Contratos e sistemas

-   Qual módulo é a fonte de verdade dos contratos: ERP ou Social
    Wiring?
-   Existe integração efetiva entre os dois módulos? Se sim, por quais
    APIs/eventos?
-   Qual sistema inicia o envelope de assinatura?
-   Como são tratados aditivos, contratos paralelos e instrumentos de
    permuta?
-   Como garantir que a versão assinada esteja associada ao processo
    correto?

### 16.4 Configuração do processo

-   Quais etapas configuráveis estão efetivamente ativas no ambiente
    atual?
-   Quais campos e documentos são exigidos para avançar entre etapas?
-   Quais etapas exigem aprovação humana?
-   Quais prazos e alertas operacionais são necessários para o Jurídico?
-   Como registrar impedimentos, pendências e dependências externas?

------------------------------------------------------------------------

## 17. Sugestões e recomendações para a continuidade

1.  **Fechar primeiro o fluxo operacional real.** Validar com a equipe
    quem executa, quem aprova e qual evidência encerra cada etapa.
2.  **Construir uma matriz de responsabilidade (RACI).** Para cada
    etapa, definir responsável pela execução, autoridade de aprovação,
    pessoas consultadas e pessoas informadas.
3.  **Definir critérios de entrada e saída por etapa.** Uma etapa deve
    ter condições objetivas para começar, avançar, retornar ou ser
    encerrada.
4.  **Formalizar o aceite da proposta como evento de transição.**
    Definir origem, permissões, dados mínimos e comportamento
    idempotente da criação do Processo de Venda.
5.  **Resolver a fonte de verdade contratual.** Não implementar
    sincronizações até entender a relação entre contratos do ERP e do
    Social Wiring.
6.  **Aproveitar a timeline existente.** Ampliar apenas se faltar algum
    evento ou evidência importante, evitando uma segunda linha do tempo.
7.  **Separar estado de negócio de estado de automação.** Um processo
    pode estar em uma etapa enquanto uma automação está desabilitada,
    pendente ou com falha.
8.  **Criar indicadores operacionais antes de automatizar tudo.** Por
    exemplo: tempo em cada etapa, pendências por responsável, contratos
    aguardando revisão, assinaturas pendentes e processos parados.
9.  **Especificar exceções.** Proposta retirada, documentação
    incompleta, divergência de partes, financiamento recusado, imóvel
    indisponível, assinatura expirada e dependência de cartório devem
    ter tratamento explícito.
10. **Só depois desenhar automações.** As automações devem refletir o
    processo aprovado, e não determinar silenciosamente como a operação
    deve funcionar.

------------------------------------------------------------------------

## 18. Próximos passos sugeridos

A sequência recomendada para retomar o trabalho em outro ambiente é:

1.  Revisar este documento e corrigir qualquer divergência com a
    operação real da One.
2.  Fechar o fluxo de qualificação, supervisão e encaminhamento ao
    corretor.
3.  Fechar o fluxo do corretor até o aceite da proposta.
4.  Definir o evento formal de aceite e os dados mínimos para abertura
    do Processo de Venda.
5.  Mapear as etapas do Jurídico, com responsáveis, entradas, saídas,
    prazos e evidências.
6.  Resolver a integração e a fonte de verdade dos contratos e
    assinaturas.
7.  Consolidar a especificação funcional do processo até a conclusão do
    Jurídico.
8.  Em uma etapa separada, iniciar o planejamento do pós-venda.

------------------------------------------------------------------------

## 19. Notas de continuidade

-   Não retomar o desenho do pós-venda nesta rodada. Ele foi
    explicitamente adiado.
-   Não reabrir o SDR da Julia como se estivesse em branco; o escopo
    atual está definido e próximo de pronto.
-   Não tratar a coleta de duas opções de horário como agendamento
    confirmado.
-   Não tratar o controle interno de chaves como confirmação de entrega
    ao comprador.
-   Não presumir que os módulos de contratos do ERP e do Social Wiring
    estão integrados.
-   Não assumir que a lista inicial de etapas do Processo de Venda é
    imutável; a implementação consultada permite configuração por
    registros de etapa.
-   Não modificar o repositório sem pedido explícito.
-   Ao continuar em outro ambiente, usar este documento como contexto de
    partida e validar os pontos em aberto antes de desenhar
    implementação.

**Fim do documento.**

------------------------------------------------------------------------

# ATUALIZAÇÃO DE CONTINUIDADE --- CONTEXTO CONSOLIDADO MAIS RECENTE

**Data da atualização:** 26 de novembro de 2026\
**Regra de precedência:** esta seção complementa o documento original e
prevalece sobre qualquer trecho anterior que esteja em conflito com as
decisões mais recentes registradas aqui. O conteúdo histórico anterior
foi preservado para rastreabilidade.

## A. Instruções obrigatórias para o próximo agente

1.  Este material é uma especificação de planejamento e transferência de
    contexto. **Não é autorização para implementar.**
2.  Não alterar o repositório GitHub `jraphaelsst/noctusai`, em nenhuma
    branch.
3.  Não criar, editar ou excluir código, migrations, tabelas,
    configurações, documentação ou arquivos do repositório.
4.  Não alterar o prompt atual da Júlia nem reconstruir o SDR. O SDR
    está praticamente pronto e deve ser preservado.
5.  Preservar o grupo/área da Júlia e os recursos existentes, inclusive
    Follow-up. Antes de qualquer proposta futura, mapear o que já existe
    para evitar duplicação.
6.  Consultas ao repositório, se autorizadas e disponíveis, devem ser
    estritamente read-only. Localizar a árvore e os caminhos reais antes
    de abrir arquivos. Não presumir paths.
7.  Não afirmar que uma funcionalidade existe apenas porque foi
    planejada. Distinguir sempre:
    -   **Implementação documentada anteriormente:** registrada na
        auditoria anterior, mas não necessariamente revalidada nesta
        sessão.
    -   **Decisão do usuário:** regra operacional expressamente
        definida.
    -   **Proposta:** recomendação técnica ainda não aprovada.
    -   **Pendente:** questão que exige decisão ou evidência.
8.  Não pedir ao usuário para repetir informações já consolidadas neste
    documento.
9.  Conduzir o planejamento de forma contínua. Fazer perguntas pontuais
    somente quando uma decisão do usuário for realmente necessária.
10. O objetivo final é entregar a outro agente uma especificação
    funcional e técnica suficientemente completa para implementação
    futura, sem que esse agente precise reconstruir o histórico das
    conversas.

## B. Correções e precedência sobre o documento anterior

O documento original descreve, em alguns trechos, validação da análise
da Júlia por Rapha seguida da escolha de um corretor. A decisão mais
recente a ser considerada para o fluxo de entrada é:

-   A Júlia encaminha a solicitação qualificada diretamente para Rapha.
-   Rapha é o destinatário operacional inicial.
-   Não existe distribuição automática para corretores nem fila
    automática nesta primeira versão.
-   O desenho de longo prazo não deve fixar Rapha permanentemente no
    código: o destinatário/responsável deve ser configurável.
-   Qualquer etapa de validação, supervisão ou seleção de corretor que
    venha a ser mantida deve ser descrita sem contradizer o
    encaminhamento direto atual e precisa ser confirmada com o usuário
    antes de ser tratada como regra final.

A referência anterior a "duas opções" de disponibilidade deve ser
entendida como uma ou, preferencialmente, duas opções de dia e horário.
A Júlia coleta disponibilidade; ela **não agenda, não confirma e não
garante a visita**.

## C. Jornada operacional da One --- escopo geral

A jornada principal está organizada em quatro grandes etapas:

1.  **SDR / Júlia:** entrada, primeiro contato, cadastro inicial,
    identificação da intenção, qualificação e coleta de intenção
    concreta de visita.
2.  **Comercial / corretor:** atendimento humano, aprofundamento da
    necessidade, seleção de imóveis, apresentação, visitas, feedback,
    proposta e negociação.
3.  **Jurídico:** documentação, análise, elaboração/revisão contratual,
    assinatura e acompanhamento das pendências jurídicas.
4.  **Finalização:** conclusão dos marcos operacionais da transação,
    respeitando as responsabilidades de cada participante.

O pós-venda é uma atuação futura, posterior à conclusão da operação. Não
deve ser confundido com a responsabilidade atual do Jurídico.

**Divisão operacional atual a preservar:** o Jurídico continua
acompanhando o cliente nas etapas jurídicas. O corretor não passa a ser
responsável pelo acompanhamento jurídico. A Júlia poderá, futuramente,
assumir comunicações de acompanhamento em outras etapas, mas não
substitui a responsabilidade técnica ou decisória dos profissionais
humanos.

## D. SDR da Júlia --- fluxo definido e protegido

O SDR atual está praticamente pronto. Não o reescrever, reconstruir ou
alterar nesta etapa de planejamento.

Fluxo operacional definido:

1.  O lead chega à One.
2.  Júlia inicia o primeiro contato.
3.  No cadastro inicial, coleta somente:
    -   nome;
    -   telefone;
    -   e-mail.
4.  Identifica a intenção comercial, sem presumir que todo contato seja
    compra. Tipos explicitamente considerados:
    -   compra;
    -   aluguel;
    -   permuta.
5.  Identifica o imóvel que originou o contato.
6.  Verifica se o cliente deseja somente o imóvel de origem ou se aceita
    conhecer outras opções compatíveis. O detalhe exato da implementação
    atual dessa escolha precisa ser conferido no fluxo real, sem alterar
    o prompt.
7.  Qualifica a necessidade e o interesse.
8.  Quando o cliente demonstra intenção concreta de visitar, Júlia
    coleta disponibilidade: uma ou preferencialmente duas opções de dia
    e horário.
9.  Nessa etapa de intenção concreta de visita/disponibilidade, solicita
    CPF e RG do cliente principal, explicando a finalidade.
10. Organiza o resumo estruturado e encaminha a solicitação diretamente
    para Rapha.
11. Rapha assume a coordenação humana e conduz a confirmação da visita.

**Limites inegociáveis do SDR:** - Júlia não agenda a visita. - Júlia
não confirma a visita. - Coletar disponibilidade não equivale a
agendamento. - Não solicitar CPF/RG no primeiro contato. - Não exigir
CPF/RG dos acompanhantes nesta primeira versão. - Se o cliente não
quiser fornecer documentos, explicar a finalidade e encaminhar para
humano, sem pressão e sem inventar exceções. - Não declarar visita
confirmada sem confirmação humana/sistema confiável.

## E. Cadastro progressivo, dados e LGPD

  -----------------------------------------------------------------------
  Momento                             Dados definidos
  ----------------------------------- -----------------------------------
  Primeiro contato                    Nome, telefone e e-mail

  Intenção concreta de visita e       CPF e RG do cliente principal
  coleta de disponibilidade           

  Acompanhantes                       Não exigir CPF/RG nesta primeira
                                      versão
  -----------------------------------------------------------------------

Requisitos de planejamento: - Cadastro inicial pode ser provisório e
incompleto. - Não exigir CPF/CNPJ para iniciar o cadastro. - Guardar
dados em campos apropriados, não apenas no texto livre da conversa. -
Controlar acesso por função e necessidade. - Definir finalidade,
retenção, segurança e trilha de acesso. - Evitar solicitar documentos
antes do momento operacional definido. - Tratar duplicidade de cadastro
com cautela; telefone, nome e e-mail podem ajudar na identificação, mas
não se deve fundir pessoas automaticamente sem regra segura. - Aplicar
minimização de dados e os princípios pertinentes da LGPD.

## F. Intenção comercial, oportunidade, visita e transação

Estas entidades/conceitos não devem ser confundidos:

-   **Cliente:** pessoa ou empresa.
-   **Jornada:** histórico amplo de relacionamento com a One.
-   **Atendimento:** interação/registro operacional no fluxo de
    atendimento.
-   **Intenção comercial:** objetivo declarado pelo cliente, como
    compra, aluguel ou permuta.
-   **Oportunidade:** avanço comercial concreto, conforme critério
    definido abaixo.
-   **Visita solicitada:** intenção de visitar acompanhada de
    disponibilidade candidata.
-   **Visita confirmada:** compromisso confirmado pela operação
    humana/sistema.
-   **Visita realizada:** visita efetivamente ocorrida.
-   **Transação:** operação específica, como compra/venda, locação ou
    operação com permuta.
-   **Processo operacional/jurídico:** conjunto de atividades para
    executar a transação.

**Decisão do usuário sobre oportunidade:** manifestar interesse genérico
em comprar, alugar ou fazer permuta não cria, por si só, uma
oportunidade. A oportunidade só se torna concreta quando o cliente chega
ao estágio de intenção concreta de visita, com disponibilidade
candidata.

**Proposta técnica ainda não ratificada:** criar/registrar a
oportunidade no momento em que a Júlia conclui a coleta necessária e
encaminha a solicitação para Rapha. Um status como
`AGUARDANDO_AGENDAMENTO` é apenas exemplo de proposta, não status
confirmado do banco nem decisão final do usuário.

Uma visita solicitada não é uma visita confirmada. Uma visita confirmada
não é uma visita realizada. Preservar cada evento e seu histórico.

## G. Encaminhamento para Rapha e futura atribuição

Fluxo atual definido: - Júlia encaminha a solicitação diretamente para
Rapha. - Rapha recebe dados de cadastro, intenção, imóvel de origem,
alternativas consideradas, resumo da qualificação e disponibilidade
candidata. - Rapha assume a coordenação e valida a disponibilidade com
as pessoas envolvidas. - A confirmação da visita ocorre na operação
humana/sistema, não por inferência da Júlia.

Não desenhar como comportamento atual: - distribuição automática por
algoritmo; - fila automática de corretores; - atribuição automática por
região, produto ou desempenho.

Recomendação para arquitetura futura, ainda não aprovada: parametrizar o
destino/responsável do encaminhamento para que a operação possa evoluir
sem hardcode. A configuração deve preservar o comportamento inicial
atual, cujo destinatário é Rapha.

## H. Continuação do processo após o encaminhamento --- ainda precisa ser detalhada

O próximo bloco de planejamento deve detalhar a atuação de Rapha após
receber a solicitação:

1.  Receber e visualizar o resumo estruturado.
2.  Verificar as opções de disponibilidade apresentadas.
3.  Validar a disponibilidade do imóvel e das pessoas necessárias (por
    exemplo, proprietário/responsável), conforme o procedimento real da
    One.
4.  Confirmar uma opção ou negociar novo horário com o cliente.
5.  Registrar a visita somente no estado correspondente à confirmação
    efetiva.
6.  Registrar resultado posterior: realizada, cancelada, não
    comparecimento ou outro resultado que a operação venha a definir.
7.  Preservar tentativas anteriores e reagendamentos na timeline.
8.  Continuar a busca e seleção de imóveis, quando o cliente aceitar
    alternativas.
9.  Registrar feedback e próximos passos comerciais.

Não presumir que todos esses estados já existem no software. A migration
anterior identificou registros de agendamento independentes associados
ao atendimento, mas não comprovou por si só um fluxo completo de status,
responsável e transições.

**Pergunta ainda pendente:** quando o cliente não comparece à visita, a
oportunidade deve retornar automaticamente para uma etapa de
reagendamento, preservando o histórico da visita não realizada, ou Rapha
deve decidir manualmente o próximo passo? Não há decisão registrada.

## I. Comercial --- do atendimento à proposta

Responsabilidade humana do corretor após o encaminhamento/atribuição
operacional: - contato e aprofundamento da necessidade; - seleção e
apresentação de imóveis; - organização e confirmação das visitas; -
acompanhamento da visita e registro do resultado; - coleta de
feedback; - manutenção de alternativas de imóveis avaliadas; -
preparação de proposta; - negociação; - registro de aceite, rejeição,
retirada ou encerramento.

Uma oportunidade pode envolver vários imóveis candidatos. Se um imóvel
for escolhido para proposta, ele passa a ser o imóvel principal daquela
operação, mas os demais imóveis avaliados devem permanecer no histórico
como alternativas consideradas.

Se um imóvel ficar indisponível: - não apagar o histórico; - registrar
motivo e momento; - notificar o responsável; - preservar a etapa
anterior e a atual; - definir com a operação se a oportunidade retorna à
busca/seleção; - exigir ciência humana quando houver ação necessária.

A proposta aceita é o marco de transição para o processo de
fechamento/jurídico, conforme o fluxo documentado anteriormente. A forma
exata de registrar o aceite, permissões, dados mínimos e exceções ainda
precisa ser fechada.

A jornada não deve pressupor que compra, locação e permuta têm processos
idênticos. Mapear variações de cada modalidade antes de fixar regras
universais.

## J. Jurídico, finalização e pós-venda

Preservar o conteúdo técnico das seções originais sobre: - abertura do
Processo de Venda após aceite; - etapas configuráveis; -
módulos/estruturas de contratos no ERP e Social Wiring; - versões de
documentos; - envelopes e signatários de assinatura eletrônica; -
necessidade de identificar a fonte de verdade contratual; - distinção
entre custódia interna de chaves e entrega formal ao comprador; -
timeline unificada e auditoria.

Esses elementos foram identificados em investigação anterior e precisam
de revalidação read-only no código antes de uma especificação de
implementação.

A jornada de finalização deve ser detalhada separadamente do Jurídico.
Não considerar que a conclusão do Jurídico prova automaticamente
registro, pagamento, transferência, posse ou entrega de chaves. Cada
marco deve ter responsável, evidência, timestamp e fonte confiável.

O pós-venda continua fora do detalhamento funcional desta rodada, mas
deve constar como fase futura na visão geral. A futura Júlia poderá
atuar em satisfação e relacionamento depois da conclusão formal da
operação.

## K. Automações futuras da Júlia e controle por configuração

Diretriz definida para planejamento: 1. Controle geral por empresa:
habilitar/desabilitar atuação da Júlia. 2. Controle por etapa:
comercial, jurídico, finalização e, futuramente, pós-venda. 3. Controle
individual por automação dentro de cada etapa.

As futuras etapas/automação devem começar desabilitadas por padrão, sem
interferir no SDR atual já existente.

Regras transversais: - desabilitar automação não apaga histórico; -
definir política para execuções em andamento ou enfileiradas; - reativar
não deve disparar mensagens antigas automaticamente; - eventos e
webhooks precisam de idempotência; - registrar tentativas, falhas,
motivo, retentativas e escalonamentos; - separar estado do processo de
negócio do estado da automação; - exigir fonte confiável e evidência
para eventos críticos; - não permitir que a IA decida sozinha o estado
jurídico/comercial; - respeitar consentimento, finalidade, horários e
preferências de contato; - aplicar acesso mínimo necessário aos dados e
documentos.

## L. Arquitetura conceitual --- não confundir com implementação confirmada

Orientação arquitetural em discussão: - **Social Wiring:**
acompanhamento operacional de atendimentos, status, eventos e histórico
do relacionamento, de acordo com o que já existe. - **Agents:**
configuração, permissões, orquestração e execução de agentes e
automações. - **ERP/CRM NoctusAI:** gestão de clientes, oportunidades,
imóveis, transações e processos de negócio.

Essa divisão é conceitual e não fecha, por si só, contratos de
integração. Antes de propor sincronizações, identificar APIs, bancos,
serviços, eventos e fontes de verdade reais. Evitar duplicar entidades
ou timelines.

## M. Estado de conhecimento e grau de certeza

### Decisões do usuário registradas

-   Quatro grandes etapas: SDR, Comercial, Jurídico e Finalização.
-   Pós-venda como etapa futura.
-   Preservar SDR atual da Júlia e não alterar seu prompt.
-   Primeiro contato coleta nome, telefone e e-mail.
-   CPF e RG somente com intenção concreta de visita e coleta de
    disponibilidade, apenas do cliente principal.
-   Júlia não agenda nem confirma visita.
-   Júlia encaminha a solicitação diretamente para Rapha no fluxo atual.
-   Não há distribuição automática para corretores nesta primeira
    versão.
-   Interesse genérico de compra/aluguel/permuta não cria oportunidade.
-   Oportunidade concreta depende de intenção de visita e
    disponibilidade candidata.
-   Jurídico continua acompanhando o cliente nas etapas jurídicas;
    corretor não assume essa função.

### Implementação documentada em auditoria anterior, não revalidada nesta atualização

-   Atendimento como cartão do funil.
-   Etapas de funil e migrations citadas no documento original.
-   Registros independentes de agendamento.
-   Registro histórico de identidade de imóvel.
-   Processo de Venda originado do aceite.
-   Etapas configuráveis do Processo de Venda.
-   Estruturas de contrato no ERP e Social Wiring.
-   Envelopes/versões de assinatura.
-   Controle interno de chaves.
-   Timeline unificada.

### Recomendações/propostas ainda não ratificadas

-   Status inicial de oportunidade, por exemplo
    `AGUARDANDO_AGENDAMENTO`.
-   Modelo final de estados da visita e reagendamento.
-   Configuração genérica do destino/responsável do encaminhamento.
-   Detalhes dos switches e política de execução pendente ao desligar
    automações.
-   Campos técnicos, eventos, payloads, APIs e contratos de integração.

### Pendências principais

1.  Tratamento de não comparecimento e reagendamento.
2.  Estados e transições de solicitação, confirmação, realização e
    cancelamento da visita.
3.  Como Rapha valida disponibilidade e registra confirmação.
4.  Critérios de qualificação e critérios de completude do resumo da
    Júlia.
5.  Como o corretor recebe e aceita a responsabilidade, se houver aceite
    formal.
6.  Variações de fluxo para compra, aluguel e permuta.
7.  Critérios e permissões para registrar proposta e aceite.
8.  Dados mínimos para abrir o processo jurídico.
9.  Mapeamento detalhado das atividades, responsáveis, prazos, entradas
    e saídas do Jurídico.
10. Fonte de verdade e integração de contratos entre ERP e Social
    Wiring.
11. Marcos e evidências da Finalização.
12. Política de automações em execução/enfileiradas quando houver
    desligamento.
13. Revalidação read-only da implementação atual e atualização da matriz
    "existe / não existe / não verificado".

## N. Próxima sequência de trabalho recomendada

Sem alterar repositório ou prompt:

1.  Fechar o fluxo pós-encaminhamento para Rapha, incluindo
    disponibilidade, confirmação e resultado da visita.
2.  Fechar estados e histórico de visitas, faltas, cancelamentos e
    reagendamentos.
3.  Detalhar o atendimento comercial até proposta e negociação.
4.  Especificar diferenças entre compra, aluguel e permuta.
5.  Formalizar aceite e transição ao processo jurídico.
6.  Mapear o Jurídico com responsáveis, entradas, saídas, documentos,
    prazos, evidências e exceções.
7.  Mapear Finalização e seus marcos formais.
8.  Definir integrações e fontes de verdade após revalidar o código.
9.  Consolidar especificação funcional e técnica para o agente de
    desenvolvimento.
10. Planejar pós-venda em etapa separada.

**Instrução de continuidade para o próximo agente:** começar pela seção
H e pela pergunta pendente de não comparecimento. Não voltar ao início
do SDR. Não solicitar que Rapha repita as decisões consolidadas. Não
implementar nada.

------------------------------------------------------------------------

# REGISTRO DE CONTINUIDADE DA CONVERSA

Na conversa de 26/11/2026, Rapha pediu explicitamente que o contexto não
se perca novamente e solicitou que este documento atualizado seja
mantido como referência persistente. Este Markdown é a fonte de
continuidade do projeto e deve ser atualizado incrementalmente quando
novas decisões forem tomadas. Em caso de divergência entre mensagens
antigas e este registro, confirmar a data e a decisão mais recente,
preservando o histórico em vez de apagar decisões anteriores.

**Limite importante:** a existência deste arquivo na Biblioteca não
garante que toda conversa futura carregará automaticamente cada detalhe.
Ao retomar o projeto, localizar e ler este documento antes de pedir
contexto ao usuário.
