---
titulo: "Produto e escopo"
tipo: guia
proveniencia:
  fonte: "limiar-app agents/nos-no-limiar/knowledge/01-produto-e-escopo.md (v0.1.0)"
  data: "2026-10-03"
---
# Produto e escopo

Fonte: `docs/spec/especificacao-mestre-v1.0.md` (§ entre parênteses).

## O que é
Produto de **bem-estar, reflexão e descoberta** para a vida adulta (§0). Núcleo: oferecer coisas
concretas para fazer, explorar, criar e pensar no tempo livre que aparece quando rotinas mudam.
JTBD (§1.3): "Quando uma rotina antiga deixa espaço e eu fico sem saber o que fazer com aquele tempo,
quero receber uma proposta simples e interessante que combine com meu momento."

## Para quem (§1.4)
Mulheres ~45–65 anos, filhos adolescentes tardios ou adultos, em mudança de rotina e identidade.
Somente **maiores de 18** (confirmação sim/não, nunca data de nascimento). Brasil, pt-BR.
A transição pode ser vivida como perda, alívio, orgulho ou liberdade — **nunca presumir sofrimento** (§1.1, §2.1).

## O que NÃO é (§1.5)
Psicoterapia, psicanálise automatizada, aconselhamento, diagnóstico, triagem, teste psicológico,
"perfil psicológico", score de humor, serviço de emergência, promessa de cura ou de efeito terapêutico,
relação de dependência com a IA.

## Estrutura (§3)
Abas: **Início · Explorar · Salvos · Perfil**. Seis mundos: Quem sou eu agora? · Minha relação com
filhos adultos · O que faço com esse tempo? · Nós dois agora (com alternativa sem parceiro) ·
Meu mundo pode aumentar · Experimenta isso.

## Recurso principal: "Me tira do sofá" (§4.3)
No máximo 4 escolhas (tempo, energia, ambiente, companhia) → **uma atividade por vez** com Bora /
Outra / Guardar. Nunca uma lista de 20 ideias.

## Catálogo (§5, §22)
Atividades estruturadas com metadados (schema §5). Nada é publicado por IA sem aprovação humana.
As 15 sementes estão em `src/data/activities.ts`, todas `rascunho` (passos escritos pelo Claude,
aguardando revisão da Mônica).

## Estado atual do app (Fase 0 — protótipo, dados locais, sem IA, sem backend)
Feito: onboarding (01–04, sem etapa de notificações), Início, Me tira do sofá (06–09), Explorar
(mundos; só "Experimenta isso" tem conteúdo), Salvos persistidos no aparelho, Perfil, Ajuda e
segurança, Sobre, Privacidade, apagar dados.
Fora da Fase 0 por regra: pergunta aberta com IA (§4.7) — só depois da camada de segurança (§25.5).
Pendente: jogos A e B, ícone/splash, testes automatizados, conteúdo dos 5 mundos "Em breve".

## Conflitos spec × mockup (C1–C12)
Por padrão **a spec vence** (§0); o mockup manda em aparência e layout. Ver
`docs/design/mockup-v0-decomposition.md` §6 e `docs/design/decisions.md`. Aguarda confirmação da Mônica.
