---
titulo: "Segurança, privacidade e limites regulatórios"
tipo: guia
proveniencia:
  fonte: "limiar-app agents/nos-no-limiar/knowledge/02-seguranca-e-privacidade.md (v0.1.0)"
  data: "2026-10-03"
---
# Segurança, privacidade e limites regulatórios

## Rotas de segurança (§8) — o app não trata crise: interrompe e encaminha
| Nível | Exemplos | Comportamento |
|---|---|---|
| Verde | saudade, domingo sem plano, conflito comum | fluxo normal |
| Amarelo | perda persistente de interesse, incapacidade funcional, usar o app no lugar de ajuda humana | não diagnosticar; reforçar limite; sugerir apoio humano |
| Vermelho | desejo de morrer, se machucar, plano/intenção | interromper tudo; sem jogo, sem atividade, sem motivacional; recursos humanos |
| Violência | agressão, ameaça, violência doméstica | Ligue 180 (orientação/denúncia); 190 em emergência |

Contatos (Brasil): **SAMU 192 · CVV 188 · Ligue 180 · Polícia 190**. Texto aprovado da tela de risco: spec §8.1.
Regras (§8.2): nunca "faça um desenho/respire" no lugar de ajuda humana; nunca pedir promessa de não
se machucar; nada promocional em fluxo de segurança; rota vermelha funciona **sem IA e offline** (§25.8).
No app: `src/app/ajuda.tsx` é estático e sempre acessível (fora dos guardas de navegação).

## IA (§7) — quando existir
Pipeline obrigatório: entrada → normalização → classificador de segurança **independente** do modelo
→ regras determinísticas → (risco alto: bloqueia) → RAG só em base curada → prompt restritivo →
pós-filtro → resposta. Resposta 80–130 palavras, no máximo 2 caminhos. Nunca falsa intimidade
("estou aqui com você"). Suíte de regressão antes de lançar (§21).

## Privacidade e LGPD (§6, §10, §14)
- Coletar o mínimo: nada de nome completo, CPF, data de nascimento, endereço, filhos, diagnóstico, medicação.
- Texto livre é **efêmero** por padrão; salvar só com ação explícita.
- **Analytics nunca recebe texto digitado**, conteúdo de crise, nomes, saúde.
- Personalização só por escolhas explícitas; nenhum perfil emocional persistente.
- Direitos: ver, editar, exportar, **apagar tudo**. No app: Perfil → "Apagar dados deste aparelho".
- Fase 0: tudo fica só no aparelho (`src/state/storage.ts`); a tela Privacidade diz exatamente isso.

## Fronteira clínica e regulatória (§9)
Se o app passar a executar métodos psicológicos como serviço, ou for apresentado como atendimento,
entra na Resolução CFP 9/2024; finalidade médica → Anvisa RDC 657/2022.
Nunca chamar jogos de "teste", "avaliação", "triagem", "escala". Nunca "baseado em psicanálise" como
selo de tratamento. **Atenção extra**: a autora é psicanalista clínica — ver `o conhecimento marca/monica-e-tese`.

## Notificações e monetização (§15, §16)
Notificações: opt-in, desligadas por padrão, no máximo 2–3/semana, sem culpa ("sentimos sua falta"),
sem horário noturno. Hoje não existem — por isso o onboarding não pergunta.
Monetização: nunca oferta após rota amarela/vermelha; nunca paywall em segurança; sem urgência falsa.
"Quero conhecer os planos" do mockup **não** é implementado sem decisão de monetização (§24 Q3).
