---
chave: precedencia
titulo: Fontes e precedência
ordem: 20
---
Quando fontes divergem, vale esta ordem:
1. **Regras de segurança, privacidade e escopo da especificação mestre** (a própria spec diz que prevalecem até revisão humana).
2. **Decisões registradas** no projeto (quem decidiu, quando, por quê) e no Decision Board.
3. **Identidade visual** do projeto (tokens de tema prevalecem sobre a documentação).
4. **Mockup** — manda em aparência e layout; nos conflitos com a spec (C1–C12), a spec vence por padrão.
5. **Base editorial da marca e tese da Mônica** — fundo conceitual, nunca enquadramento clínico.

Os aprendizados mais novos do seu registro prevalecem sobre texto mais antigo do conhecimento.
Quando duas fontes se contradizem, cite as duas e diga qual prevalece. Se a ordem não resolver, é **decisão pendente**: descreva opções, recomende, não decida.
O contexto do projeto é a sua fonte de verdade sobre o estado atual — consulte antes de afirmar como algo está:
- especificação mestre: `docs/spec/especificacao-mestre-v1.0.md`
- decisões registradas: `docs/design/decisions.md`
- Decision Board (pendências e decididos): `docs/design/decision-board.json` — **abra antes de citar qualquer item como pendente**
- identidade visual: `docs/design/visual-identity.md` e `src/theme/` (o código prevalece)
- mockup e conflitos C1–C12: `docs/design/mockup-v0-decomposition.md`
- código do app: `src/` (telas em `src/app/`, conteúdo em `src/data/`)
