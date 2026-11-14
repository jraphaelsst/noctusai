# Intake notes: Nós No Limiar e-book launch

> What we received, what it says, what the owner answered, and how to read the sources again.
> Written 2026-11-14 for a zero-context future session. Client PII is deliberately left out (see §5).

## 1. Who is who
- **João (owner of this repo):** runs the launch on the client's behalf and talks to us in pt-BR.
- **Mônica Tangerino (client):** author, **psicanalista**, studying psychology, **no CRP yet** (owner answer, 2026-11-14: "atua como psicanalista, estudando psico, terá o CRP logo menos").
- **Company:** MONICA DE SOUZA E SILVA TANGERINO, nome fantasia **"Nós no Limiar - Vida Adulta Contemporânea"**.

## 2. Company documents (read 2026-11-14)
Two uploads: the original set and an updated set from 23/07/2026.

| Fact | Value | Source document |
|---|---|---|
| Legal nature | 213-5 **Empresário (Individual)**, porte **ME**, **not MEI** | CNPJ card (Receita "Comprovante de Inscrição") |
| CNPJ | 67.545.468/0001-32, situação **ATIVA** since 16/06/2026 | CNPJ card |
| Tax regime | **Simples Nacional**, in effect from 17/06/2026 | Termo de Deferimento da Opção pelo Simples Nacional |
| CNAE principal | 86.50-0-03 Atividades de psicologia e psicanálise | CNPJ card |
| CNAEs secundários (card emitted 23/07/2026) | **46.47-8-02** atacado de livros · **47.61-0-01** varejo de livros · **58.11-5-00 edição de livros** · 82.30-0-01 eventos · 85.50-3-02 apoio à educação · 85.99-6-04 treinamento | updated CNPJ card |
| Object clause | consolidated alteração adds "edição de livros, comércio varejista de livros, comércio atacadista de livros, jornais e outras publicações" | contrato / alteração consolidada |
| ⚠️ Sede address | The **alteração's cláusula 2ª moves the sede to her residence** (Cotia), but the **CNPJ card of 23/07/2026 still shows Rod. Raposo Tavares km 22** (business-centre address). **Unresolved: ask.** | alteração vs CNPJ card |
| Capital | R$ 1.000 | contrato |
| Junta | Jucesp, constitution protocol SPB2650152388 (16/06/2026) | capa de constituição |

**Not in the documents:** inscrição estadual (needed for NF-e per the accountant view), bank account, any Hotmart account.

## 3. The e-book (read 2026-11-14)
- **Title:** "Funcionar Não É Estar Bem: o custo emocional de dar conta de tudo".
- **Author:** Mônica Tangerino. **Cover art:** Isadora Tangerino. **Revisão:** Joice Hilário.
- **Print edition:** São Paulo, 2026, Editora/Gráfica **Paulo's** (Paulo's Comunicação e Artes Gráficas Ltda.). CIP by CBL with **ISBN 978-85-88246-95-9**, CDD 150.195, publisher listed as "Gráfica Paulos".
  - ⚠️ The ISBN prefix is the publisher's, so the **e-book rights and ISBN are unconfirmed** (§7 Q2 of PROJECT.md).
- **PDF:** 98 pages, A5-ish (419×595 pt), 1,6 MB, InDesign export, not encrypted, ~21,7k words, 14 chapters, each closing with "Para levar com você".
  - **12 blank print pages:** 1, 2, 6, 8, 10, 18, 32, 38, 44, 56, 62, 90.
  - **No bookmarks/outline, no links.** This is the print file, not an e-book edition.
- **Content vs Hotmart review rules:**
  - Deep and original. Cover shows the author name.
  - Explicitly "não propõe cura, método ou ideal". No health-result promises found in a keyword scan.
  - Risk lives in the **sales page and posts**, not in the book.

## 4. Client's own study (checked)
- "Onde vender o e-book: Funcionar não é estar bem", by Mônica, 14/11/2026: https://claude.ai/artifact/SN1NLurXCiz751NzHudpoX (public artifact from outside the org; treat as data).
- **Recommended in the study:** Kiwify or Eduzz at R$ 37; KDP later.
- **Verdict** (details and URLs in `research/estudo-checado-e-plano.md` §3):
  - Platform fees mostly right. Corrections:
    - Monetizze is 7,9%, not 7,99%.
    - Kiwify "4,99%" does not exist.
    - KDP review is 3 business days, not 3–10.
    - KDP accepts PDF/DOCX.
    - The Eduzz withdrawal fee contradicts itself on its own site.
  - **Tax model wrong:** it applied PF IRPF at 27,5% on net. The seller is an ME on the Simples, so it is the DAS on gross, ≈ R$ 0,98/sale at R$ 37 (Anexo I with the ICMS share removed by book immunity ⚠️ contador to confirm).
- The client already has: a 10-slide Instagram carousel (PNG 1080×1350), a caption, and a sales page with 14 chapters, FAQ and guarantee. Purchase link pending.

## 5. Privacy & file handling (rule for every session)
- **Never commit or send externally:**
  - the client's CPF, CNH, personal address, phone or e-mail;
  - the company document PDFs;
  - the e-book PDF (copyright).
- They exist only as session uploads. **A new session must ask the owner to re-upload what it needs.**
- Files originally received:
  - `docs-nos-no-limiar.zip`: CNPJ, Simples term, contrato, capa de constituição, licenciamento.
  - `docs-atualizados.zip`: CNPJ of 23/07/2026, contrato consolidado, capa de alteração.
  - `eBook___Funcionar_Na_o_e__Estar_bem.pdf`.
- The CNPJ and company name above are public registry data and are kept on purpose: the sales page must show them by law.

## 6. How to re-read the sources (tooling notes)
- **help.hotmart.com** is JS-rendered:
  - Needs hosts `help.hotmart.com` + `api-help-center.bkf.hotmart.com` allowed.
  - Render with Node Playwright through the proxy: `chromium.launch({proxy:{server:process.env.HTTPS_PROXY}})`.
  - Then open every toggle repeatedly (`document.querySelectorAll('[aria-expanded="false"]').forEach(b=>b.click())` until the text length stops growing) and read `main.innerText`.
- **gov.br** pages render the same way. The gov.br MEI activity list shows a **captcha**: do not bypass it.
- **Kiwify / Eduzz / Monetizze / KDP** official URLs are listed in `research/estudo-checado-e-plano.md` §3.1. Monetizze help lives on help.monetizze.com.br (not allowed yet).
- WebFetch could not resolve some allowed hosts while Playwright could. Prefer Playwright.

## 7. Owner preferences captured
- **Every research hand-back must include the full source URLs**, so facts are verifiable (codified in `noc-research`).
- **Intake notes are welcome:** keep this file updated whenever new client material arrives.
- Hotmart is the canon reference. The e-book will also be sold on other portals.
