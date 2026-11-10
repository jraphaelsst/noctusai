# LGPD: a linha pessoal do Assistant no modo sombra (D46)

> Relatório do `legal-advisor` (somente leitura), 10/11/2026, a pedido do branch steward de
> `feat/assistant-chatbot`. Guardado sem alterações. Orientação, não parecer jurídico. Os pontos
> marcados para advogado (OAB) ou encarregado precisam da assinatura deles antes do go-live.

**Vale para:** 10/11/2026 · LGPD (Lei 13.709/2018) · Res. CD/ANPD 2/2022, 18/2024 e 19/2024 · produto `assistant` · WhatsApp pessoal do dono via WAHA. Fontes lidas em 10/11/2026.

## Em linguagem simples
Não dá para contar com a exceção de "uso pessoal". Os dados vão servir de base de avaliação para um produto, rodam na plataforma da empresa e seguem para LLMs no exterior. Por isso, o tratamento entra na LGPD inteira. Dá para entrar no ar com segurança se o volume e o tempo de guarda forem reduzidos, se houver um teste de legítimo interesse escrito e se os contratos com os provedores de LLM estiverem cobertos.

## 1. Art. 4, I: onde fica a linha
- Texto da lei: a LGPD não se aplica ao tratamento "realizado por pessoa natural para fins **exclusivamente** particulares **e** não econômicos" [norma, Planalto].
- O dono lendo o próprio WhatsApp no celular está **dentro** da exceção.
- Neste projeto, os dados alimentam um conjunto de avaliação para um produto futuro da NoctusAI. Isso é uma finalidade econômica, e basta uma finalidade econômica para afastar o "exclusivamente". Rodar na infraestrutura da empresa e mandar para fornecedores no exterior reforça essa leitura. **Conclusão: fora da exceção** [interpretação do texto; a ANPD não publicou orientação específica. Status: em aberto, para o advogado].
- A linha prática: se o dado sai do uso pessoal e passa a servir à empresa ou a um produto, a LGPD se aplica por inteiro.

## 2. Como a lei se aplica
- **Controlador:** quem decide a finalidade "avaliar o classificador para um produto". Isso é a NoctusAI, ou o dono como empresário enquanto não houver CNPJ. Não é o dono como pessoa privada. Registrar isso por escrito. A Supabase e os provedores de LLM são operadores ou suboperadores.
- **Base legal para dados de terceiros:** legítimo interesse (art. 7, IX), com o teste de ponderação do art. 10.
  - Coletar só o estritamente necessário (art. 10 §1).
  - Garantir transparência (art. 10 §2).
  - A ANPD pode pedir o RIPD (art. 10 §3).
  - Consentimento de cada interlocutor não é viável.
- **Transparência:**
  - Seção no aviso de privacidade da NoctusAI sobre o Assistant.
  - Uma linha no "recado" (status) do WhatsApp com o link para esse aviso.
  - Canal de contato para pedidos dos interlocutores (art. 10 §2; art. 18).
- **Dados sensíveis (art. 11):** conversas trazem saúde, religião, vida sexual etc. O art. 11 vale para qualquer tratamento que "revele" esses dados (§1). O legítimo interesse **não** está entre as bases do art. 11, e nenhuma hipótese do inciso II cobre avaliar um classificador. Na prática:
  - descartar ou mascarar esse conteúdo no conjunto de avaliação;
  - não fazer nenhum perfil de pessoas;
  - mensagens de crianças (art. 14) recebem a mesma regra: excluir.
- **Transferência internacional (arts. 33–36; Res. 19/2024):**
  - A Res. 19/2024 exige **as duas coisas**: uma base legal e um mecanismo de transferência.
  - O art. 33, IX só alcança as bases do art. 7, II, V e VI. Não alcança o legítimo interesse.
  - Sobra o art. 33, II, "b": as **cláusulas-padrão da ANPD (Anexo II da Res. 19/2024)** nos contratos com a OpenAI e a Anthropic. As DPAs desses provedores costumam usar as SCCs da UE. Saber se isso atende à norma brasileira está **em aberto**.
  - A Res. 19/2024 também exige uma página pública em português sobre a transferência (art. 17 §§2–3).
  - O prazo de adaptação dos contratos antigos venceu em 2025. **Confirmar a data exata.**
- **RIPD:** recomendado. A ANPD trata como alto risco um critério geral combinado com um específico. Aqui há tecnologia emergente (LLM) e possíveis dados sensíveis. Isso também afasta os prazos em dobro de agente de pequeno porte (Res. 2/2022, arts. 3–4).

## 3. Salvaguardas mínimas
- **Minimização:**
  - Ignorar grupos, status e listas de transmissão já na entrada. Não armazenar.
  - Começar só com conversas individuais.
  - Considerar uma lista de exclusão: família, saúde, advogado, contas bancárias.
- **Pseudonimização:**
  - Nas linhas do conjunto de avaliação, guardar o telefone como HMAC com chave separada, nunca o número em claro.
  - Nome do contato fora.
  - Enviar ao LLM só o texto, sem o número.
- **Retenção:**
  - Mensagens brutas: 90 dias.
  - Rótulos e conjunto pseudonimizado: até o fim da etapa L4, com teto de 12 meses.
  - Exclusão automática agendada e registro dela (art. 15–16).
  - Os prazos são provisórios. O advogado decide.
- **Acesso:**
  - Somente o administrador (o dono). RLS e nível de acesso declarados.
  - Registro de quem leu e quando (log de leitura).
  - Nada de dados reais em logs, commits ou memória.
- **Provedores de LLM:**
  - Usar a API comercial: sem treino nos dados por padrão. Confirmar por escrito nos termos e na DPA vigentes.
  - Pedir retenção zero se estiver disponível.
  - Teto de custo já previsto em C3.
- **Direitos (art. 18):**
  - Procedimento para apagar tudo de um número a pedido: brutos, classificações, respostas-sombra e rótulos.
  - Prazo de resposta de 15 dias para confirmação e acesso completo (art. 19, II).
- **ROPA (art. 37):** uma entrada com finalidade, base legal (legítimo interesse, com o teste), categorias de titulares (interlocutores, dono), dados, operadores (Supabase, VPS, OpenAI, Anthropic), destino EUA com o mecanismo, retenção e segurança.

## 4. Termos de uso do WhatsApp
**Confirmado, com ressalva.**
- **Contrato:** os Termos (versão não-UE, de 04/01/2021) proíbem:
  - acessar o serviço "por meios automatizados ou não autorizados";
  - "coletar informações de usuários" sem autorização;
  - fazer engenharia reversa.
  O WhatsApp pode suspender ou encerrar a conta "a qualquer momento". O risco real é **perder o número pessoal**, e o modo só-leitura não elimina esse risco.
- **Crime:** não vejo crime.
  - O dono usa a própria conta. Não há violação de dispositivo alheio (CP, art. 154-A).
  - Ele é parte das conversas: gravar comunicação de que se é parte é lícito segundo o STF (RE 583.937, Tema 237). Citação não verificada hoje: [doutrina], confirmar.
  - A Lei 9.296/96 trata de interceptação por terceiro, o que não é o caso.

## 5. Quem decide ou assina
**Advogado (OAB):**
- leitura do art. 4, I;
- o teste de legítimo interesse;
- tratamento de dados sensíveis incidentais;
- o mecanismo de transferência por provedor (Anexo II da Res. 19/2024 frente à DPA do provedor);
- os prazos de retenção;
- o texto do aviso de privacidade.

**Encarregado:**
- RIPD;
- entrada no ROPA;
- canal de atendimento aos titulares;
- ato formal de nomeação (Res. 18/2024, art. 3). Hoje o dono acumula controlador e encarregado; ver o conflito de interesses do art. 19 §1 II.

**Dono:** aceitar o risco de suspensão do número.

## Checklist para entrar no ar
1. Controlador e finalidade definidos por escrito (NoctusAI ou dono empresário).
2. Teste de legítimo interesse assinado.
3. RIPD resumido.
4. Entrada no ROPA.
5. Filtro na entrada: sem grupos, status ou transmissão. Lista de exclusão aplicada.
6. Pseudonimização (HMAC) e LLM recebendo só o texto.
7. Regra de sensíveis e menores: descartar ou mascarar.
8. Exclusão automática: 90 dias para brutos, 12 meses para o conjunto de avaliação.
9. RLS só para o administrador e log de leitura.
10. DPAs da OpenAI e da Anthropic arquivadas, com "sem treino" e mecanismo de transferência válido (ou pendência aceita pelo advogado).
11. Aviso de privacidade com a seção de transferência internacional (Res. 19/2024, art. 17) e link no recado do WhatsApp.
12. Procedimento de exclusão por número testado.
13. Risco dos Termos do WhatsApp aceito por escrito pelo dono.

## Em aberto
- Posição da ANPD sobre o art. 4, I.
- Se as SCCs da UE dos provedores atendem à Res. 19/2024.
- O prazo de adaptação da Res. 19/2024.
- Confirmação do RE 583.937.

## Mudanças propostas (para o tech-lead)
- **Documentação (KB `lgpd-privacy-program.md`):** acrescentar ao §2 a linha "assistant: controlador NoctusAI, legítimo interesse, transferência para os EUA" e incluir o Assistant na matriz de provedores do §9.
- **Código:** filtro de grupos e status na entrada, HMAC do telefone, job de retenção e endpoint de exclusão por número. Responsáveis: S2/S3.

## Fontes
- Lei 13.709/2018, Planalto (arts. 4, 6, 7, 10, 11, 33): https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- Termos do WhatsApp: https://www.whatsapp.com/legal/terms-of-service
- Res. ANPD 2/2022, 18/2024 e 19/2024, via KB `PATTERNS/legal/lgpd-privacy-program.md` §§5, 9, 11 (texto no DOU não relido hoje)
- Contexto do projeto: `project-history/assistant-chatbot/phase0-d46-shadow-line.md` (gap 9)
