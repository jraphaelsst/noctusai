# ERP seed — market research brief (2026-10-14)

> Companion to the commerce seed brief ([`commerce-seed-2026-10-market-brief.md`](commerce-seed-2026-10-market-brief.md)). Web research done 2026-10-14; **every URL below accessed 2026-10-14**. Sources: vendor official pages and help centres; Receita Federal, Simples Nacional, CONFAZ, the NF-e portal, eSocial, BCB, FEBRABAN and CFC for rules. Anything not confirmed on such a page is marked **NF** (not found). NF means "not documented where we looked", not "absent".
>
> **Fiscal and legal points must be confirmed by each client's contador (CRC) before they drive behaviour.** They are inputs to design, not settled answers.
>
> **Source abbreviations:**
> - **[P&R-SN]**: Perguntas e Respostas Simples Nacional (SE-CGSN, partially updated 09/10/2026), https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/PerguntaoSN.pdf
> - **[P&R-MEI]**: Perguntas e Respostas MEI/SIMEI (updated 29/04/2025), https://www8.receita.fazenda.gov.br/simplesnacional/arquivos/manual/perguntaomei.pdf
> - **[P&R-PJ]**: RFB Perguntas e Respostas PJ 2024, https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/ecf/2024-perguntas-e-respostas-da-pessoa-juridica.pdf
>
> **Caveats:**
> - Planalto (LC 123, CC, CTN) and the consolidated Res. CGSN 140/2018 text were unreachable. Those articles are cited through the official RFB/CGSN Q&As, which quote them.
> - TOTVS pages returned HTTP 402, so TOTVS facts come from official-domain search snippets (lower confidence).

## A. Vendor landscape and module taxonomy

**Two families in the Brazilian SMB market:**
- **Operational ERPs.** Stock, sales, fiscal and finance: Bling, Olist ERP (formerly Tiny), Omie, Conta Azul.
- **Finance-only tools.** AP/AR, reconciliation and DRE, no stock or NF-e: Nibo, Granatum.

Sankhya and TOTVS are mid-market and sold by quote. Odoo and ERPNext are the generic international taxonomies.

**Generic reference taxonomies**
- **Odoo apps** (https://www.odoo.com/page/all-apps):
  - Finance: Accounting, Invoicing, Expenses, Sign, Spreadsheet, ESG
  - Sales: CRM, Sales, Subscriptions, POS Shop, POS Restaurant, Rental
  - Websites: Website, eCommerce, Events…
  - Supply Chain: Inventory, Manufacturing, Maintenance, PLM, Quality, Purchase
  - HR: Employees, Payroll, Recruitment, Time Off, Appraisals, Fleet
  - Marketing: Social, Email, SMS, Automation, WhatsApp, Surveys
  - Services: Project, Timesheets, Planning, Appointments, Live Chat, Helpdesk
  - Productivity: AI, Discuss, VoIP, IoT, Documents, Knowledge
  - Customization: Studio
- **Odoo Brazil localization** (https://www.odoo.com/documentation/18.0/applications/finance/fiscal_localizations/brazil.html):
  - Modules `l10n_br*` cover NF-e, NFS-e and NFC-e (POS), plus `*_fiscal_reform` modules.
  - Taxes are computed by Avalara AvaTax, paid per call in IAP credits.
  - NFS-e cannot be cancelled electronically.
  - A SPED file export is NF.
- **ERPNext** (https://frappe.io/erpnext/pricing): Accounting, Procurement, Sales, CRM, Stock, Manufacturing, Projects, Assets, Point of Sale, Quality, Support, HR & Payroll, No-Code Builder. Budgets: https://docs.frappe.io/erpnext/user/manual/en. An official Brazil fiscal localization is NF.

### A.1 Module × vendor matrix

Legend: **Y** = confirmed on an official page · **+** = add-on or third-party · **T** = gated to a higher tier · **NF** = not found.

| Module | Bling | Olist/Tiny | Omie | Conta Azul | Nibo | Granatum | Sankhya | TOTVS small | Odoo | ERPNext |
|---|---|---|---|---|---|---|---|---|---|---|
| AP/AR | Y | Y | Y | Y | Y | Y | Y (finance) | Y (finance) | Y | Y |
| Cash flow | Y | Y | Y | Y | NF¹ | Y | NF | NF | NF | NF |
| Bank reconciliation (OFX) | T Titânio+ | T Construa+ | Y | Y | Y | Y | NF | NF | NF | NF |
| Open Finance / bank feeds | Own digital account only | NF | Y (blog) + bank integrations | Y (10 banks) | Accountant product only | NF | NF | NF | NF | NF |
| DRE / reports | T Titânio+ | T Construa+ | Y | Y (+ DRE by cost centre) | managerial | Y | NF | NF | NF | NF |
| Budgeting | NF | NF | + (Senseboard) | via cost centres | T Premium | Y | NF | NF | NF | Y |
| Cost centres | NF | Y | Y ("departamentos") | Y (rateio) | T Plus | Y (blog) | NF | NF | NF | NF |
| Quotes | Y | Y | NF | NF | — | — | Y (sales) | Y (Faturamento) | Y | Y |
| Sales orders | Y | Y | Y | Y | — | — | Y | Y | Y | Y |
| CRM-lite | + | + | Y | NF | — | — | + (Ploomes) | T PRO | Y | Y |
| Purchasing / POs / suppliers | Y | Y | Y (suggest + approval) | Y | — | — | Y | Y | Y | Y |
| Inventory, multi-warehouse | Y (unlimited) | Y | Y | Y | — | — | Y | Y | Y | Y |
| Lots / expiry | Y | + | Y (FEFO/FIFO) | NF | — | — | NF | NF | NF | NF |
| Serial numbers | NF | Y | + | NF | — | — | NF | NF | NF | NF |
| Kardex / custo médio | custo médio Y; kardex NF | NF | Y (kardex + CMC) | custo médio Y | — | — | NF | NF | NF | NF |
| Kits / variations | NF | NF | NF | Y | — | — | NF | NF | NF | NF |
| BOM / production | Y | Y (Bloco K post) | Y (production) | NF | — | — | mentioned | T PRO (OP) | Y | Y |
| NF-e | Y | Y | Y | Y | NF | NF | NF by name | NF | Y | NF |
| NFC-e | Y | Y | not confirmed (import only) | Y | NF | NF | NF | NF | Y (POS) | NF |
| NFS-e | Y | Y | Y | Y | Y | on request | NF | NF | Y | NF |
| CT-e / MDF-e | + (LOG CT-e) | NF | MDF-e Y, CT-e + | NF | NF | NF | NF | NF | NF | NF |
| SPED EFD / SINTEGRA | partial SPED + SINTEGRA | Y / Y | Y via OneFlow (incl. Bloco H/K) | NF | NF | NF | Y ("Asis") | NF | NF | NF |
| Service orders (OS) | Y | Y | NF | NF | NF | NF | NF | NF | Helpdesk / Project | Support |
| Contracts / recurring billing | Y | Y | Y | Y | Y | NF | + (Ploomes) | T PRO | Y (Subscriptions) | NF |
| Payroll / HR | NF | NF | NF | NF | NF | NF | Y (Pessoas+) | NF | Y | Y |
| Fixed assets | NF | NF | NF | NF | NF | NF | NF | NF | NF | Y |
| Projects / time | NF | NF | as a reporting dimension | NF | NF | NF | Y (services) | NF | Y | Y |
| POS / PDV | Y | Y (+R$50 per extra card integration) | T Multivarejo | NF | — | — | NF | Y (frente de caixa) | Y | Y |
| Marketplace / e-commerce hub | Y (250+ extensions) | Y (40+) | T Multivarejo | Y ("100+ integrations") | — | — | + (Magis5) | NF | own eCommerce | NF |
| Accountant portal / export | Y ("Meu Contador", XML/SPED) | partner program | Y (Painel + Domínio/Questor/Alterdata/Contmatic) | Y (Domínio integration + file export) | Y (Domínio + 50 systems) | NF | Y (accounting) | NF | — | — |
| Multi-company | T (3/5/7 accounts) | T Construa+ | Y (blog) | via Conta Azul Mais (accountants) | NF | NF | NF | NF | T Custom | NF |
| Permissions / audit log | Y / Y (admin) | Y (IP + time-of-day) / NF | Y / NF | NF | T Plus / NF | NF | Y | NF | NF | NF |
| BI / dashboards | T ("Meu Negócio") | Y | custom reports | Y | Y | Y | Y | NF | NF | NF |
| AI | Y (credits per tier + Bling MCP) | Y ("Lis" executes actions) | Y (Omie.IA Fiscal: product tax classification) | Y (invoice capture, entries) | NF | NF | Y (BIA) | NF | Y (AI app) | NF |
| Pix / boleto | Y (via Conta Digital) | Y | Y | boleto Y | boleto Y | Y / Y | NF | NF | NF | NF |

¹ Nibo's plan-comparison grid is an image; cash flow appears only as a navigation link.

**Sources by vendor**

- **Bling**
  - Pricing: https://www.bling.com.br/planos-e-precos
  - Finance: https://www.bling.com.br/funcionalidades/gestao-financeira
  - Reconciliation: https://ajuda.bling.com.br/hc/pt-br/articles/360051642334
  - DRE: https://ajuda.bling.com.br/hc/pt-br/articles/360035868954
  - Quotes: https://www.bling.com.br/funcionalidades/propostas-comerciais
  - Purchase orders and lots: https://ajuda.bling.com.br/hc/pt-br/articles/32537052882967 · https://ajuda.bling.com.br/hc/pt-br/articles/32533780576663
  - Custo médio: https://ajuda.bling.com.br/hc/pt-br/articles/360056093354
  - Production: https://ajuda.bling.com.br/hc/pt-br/articles/360051475753
  - NFS-e: https://www.bling.com.br/funcionalidades/nota-fiscal-servico-eletronica
  - CT-e: https://ajuda.bling.com.br/hc/pt-br/articles/360047140213
  - SPED: https://ajuda.bling.com.br/hc/pt-br/articles/360036583373
  - SINTEGRA: https://ajuda.bling.com.br/hc/pt-br/articles/4462068755479
  - Service orders: https://www.bling.com.br/funcionalidades/ordem-servico
  - Contracts: https://ajuda.bling.com.br/hc/pt-br/articles/360037229194
  - PDV: https://www.bling.com.br/loja-fisica
  - Multichannel: https://www.bling.com.br/vendas-multicanal
  - Accountant: https://ajuda.bling.com.br/hc/pt-br/articles/360059947433
  - Permissions: https://ajuda.bling.com.br/hc/pt-br/articles/360035558634
  - Activity log: https://ajuda.bling.com.br/hc/pt-br/articles/360039073174
  - Conta Digital: https://www.bling.com.br/funcionalidades/conta-digital
- **Olist ERP**
  - Plans: https://olist.com/planos/ (tiny.com.br/planos redirects here)
  - Feature list: https://olist.com/sistema-erp/
  - Reconciliation: https://olist.com/sistema-erp/conciliacao-bancaria/
  - Finance and cost centres: https://olist.com/lp/controle-financeiro/
  - Quotes: https://ajuda.olist.com/pedidos/propostas-comerciais-inclusoes
  - CRM: https://ajuda.olist.com/pedidos/crm-customer-relationship-management
  - Stock API: https://tiny.com.br/api-docs/api2-produtos-estoque
  - Lots: https://ajuda.olist.com/produtos/controle-de-lotes-e-validades-de-produtos
  - Serial numbers: https://olist.com/blog/olist/tiny-news/tiny-versao-333/
  - Bloco K: https://olist.com/blog/olist/tiny-news/spedfiscal-bloco-k/
  - SINTEGRA: https://ajuda.olist.com/tributos-e-obrigacoes-com-o-fisco/sintegra
  - Service orders and contracts: https://ajuda.olist.com/gerenciamento-da-conta/configuracoes-do-erp
  - Users and permissions: https://ajuda.olist.com/gerenciamento-da-conta/usuarios-uso-e-configuracoes
- **Omie**
  - Pricing: https://www.omie.com.br/precos/
  - Features: https://www.omie.com.br/funcionalidades/
  - Reconciliation: https://ajuda.omie.com.br/pt-BR/articles/6506873
  - Open Finance: https://www.omie.com.br/blog/omie-reforca-atuacao-no-open-finance-e-amplia-parceria-com-bancos/
  - DRE: https://ajuda.omie.com.br/pt-BR/articles/6672272
  - Cost centres (departamentos): https://ajuda.omie.com.br/pt-BR/articles/6590614
  - Budgeting partner app (Senseboard): https://store.omie.com.br/apps/sense-board
  - CRM: https://ajuda.omie.com.br/pt-BR/articles/8558079
  - Stock locations: https://ajuda.omie.com.br/pt-BR/articles/1592576
  - Lots: https://ajuda.omie.com.br/pt-BR/articles/11962585
  - Serial numbers (iApp PCP): https://store.omie.com.br/apps/iapp-pcp
  - Kardex and CMC: https://ajuda.omie.com.br/pt-BR/articles/6845092
  - NF-e: https://ajuda.omie.com.br/pt-BR/articles/6866038
  - MDF-e: https://ajuda.omie.com.br/pt-BR/articles/6590314
  - Fiscal / SPED via OneFlow: https://ajuda.omie.com.br/pt-BR/collections/2042762-fiscal
  - Projects: https://ajuda.omie.com.br/pt-BR/articles/6846485
  - Multi-company: https://www.omie.com.br/blog/erp-multiempresa-gestao-de-varios-cnpjs-em-um-sistema/
  - Permissions: https://ajuda.omie.com.br/pt-BR/articles/4826048
  - Pix charges: https://ajuda.omie.com.br/pt-BR/articles/10357608
- **Conta Azul**
  - Plans: https://contaazul.com/planos/
  - Homepage: https://contaazul.com/
  - Stock: https://contaazul.com/controle-estoque/
  - OFX import: https://contaazul.com/funcionalidades/importar-arquivo-ofx/
  - Open Finance: https://ajuda.contaazul.com/hc/pt-br/articles/45352937618701
  - Cost centres: https://ajuda.contaazul.com/hc/pt-br/articles/44330626479629
  - Reports: https://contaazul.com/funcionalidades/relatorios/
  - BPO / Conta Azul Mais: https://contaazul.com/bpo-financeiro/
- **Nibo:** https://www.nibo.com.br/empresa/planos-e-precos · https://www.nibo.com.br/sobre-o-nibo
- **Granatum:** https://www.granatum.com.br/financeiro/precos-planos · https://www.granatum.com.br/blog/centro-de-custo
- **Sankhya:** https://www.sankhya.com.br/software-de-gestao-erp/erp-para-gestao-empresarial/produtos/sankhya/ · https://www.sankhya.com.br/empresa/
- **TOTVS:** https://www.totvs.com/sistemas-pequenas-empresas/ · https://www.totvs.com/erp-cloud/ · https://www.totvs.com/sistema-de-gestao/totvs-backoffice-linha-protheus/

**Observed pattern:**
- Every operational ERP ships the same core: finance + reconciliation + DRE, sales orders, purchasing, multi-warehouse stock with custo médio, NF-e/NFC-e/NFS-e, a PDV, a marketplace hub, an accountant export, and permissions.
- Payroll and fixed assets are absent across all four operational ERPs. Payroll is left to the accountant.
- Odoo and ERPNext are the only ones with payroll, fixed assets and projects as first-class modules.

## B. Table-stakes vs mid-size, and the legal obligations behind each module

### B.1 Obligations by regime (what the ERP must produce data for)

| Obligation | MEI | Simples (ME/EPP) | Lucro Presumido | ERP module that feeds it |
|---|---|---|---|---|
| **NF-e (model 55)** | Not required for sales to individuals (PF). Required to a buyer with a CNPJ unless the buyer issues an entry invoice (Res. CGSN 140 art. 106) [P&R-MEI 3.6/3.7]. | Where CONFAZ rules or state law require it (Res. 140 art. 79) [P&R-SN 11.5]. | State law. | Fiscal |
| **NFC-e (model 65)** | Same exemption for sales to PF. | SP: CF-e-SAT forbidden from 01/01/2026 (Portaria CAT 147/2012 art. 34-D) → NFC-e or NF-e. https://legislacao.fazenda.sp.gov.br/Paginas/RC32089_2025.aspx · https://portal.fazenda.sp.gov.br/servicos/sat | Same. | Fiscal + POS |
| **NFS-e Nacional** | Mandatory since 01/09/2023 for service providers (Res. CGSN 169/2022). https://www.gov.br/nfse/pt-br/noticias/resolucao-cgsn-no-169-traz-novos-beneficios-ao-mei | **Mandatory through the national emitter from 01/11/2026** (Res. CGSN 191/2026). https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/simples-nacional-nfs-e-nacional-sera-obrigatoria-para-me-e-epp-a-partir-de-1o-de-novembro-de-2026 | Municipalities had to join the national standard from 01/2026 (LC 214 art. 62). https://www.gov.br/fazenda/pt-br/assuntos/noticias/2025/agosto/a-partir-de-janeiro-de-2026-a-nota-fiscal-de-servico-eletronica-nfs-e-sera-obrigatoria-a-fim-de-simplificar-cotidiano-das-empresas | Fiscal (already `NfseMode.NACIONAL` in seed) |
| **CT-e (model 57)** | — | ICMS taxpayers providing transport services (Ajuste SINIEF 09/07). https://www.confaz.fazenda.gov.br/legislacao/ajustes/2007/aj_009_07 | Same. | Fiscal, logistics market only |
| **MDF-e** | Exempt from the own-vehicle case (Ajuste SINIEF 21/10, cl. 3-A, II-a). | CT-e issuers, and NF-e issuers moving goods in their own or leased vehicles; a state may also require it intrastate. https://www.confaz.fazenda.gov.br/legislacao/ajustes/2010/aj_021_10 | Same. | Fiscal, businesses that deliver goods themselves |
| **Books** | Relatório Mensal de Receitas Brutas (Res. 140 Annex X), invoices attached, filled by the 20th of the next month (arts. 106, 108, 109) [P&R-MEI 3.6]. https://www.gov.br/pt-br/servicos/baixar-relatorio-mensal-de-receitas-brutas | Res. 140 **art. 63** [P&R-SN 11.2]:<br>• Livro Caixa (not needed if Diário + Razão are kept)<br>• Registro de Inventário at 31/12 (ICMS taxpayers)<br>• Registro de Entradas (ICMS taxpayers)<br>• Registro de Serviços Prestados / Tomados (ISS taxpayers)<br>A missing Livro Caixa is grounds for exclusion [P&R-SN 12.5]. | Registro de Inventário at year end [P&R-PJ Q037]; EFD replaces it. | Finance (Livro Caixa), Inventory (inventory book), Purchasing (entries) |
| **Full accounting** | No. | Optional simplified accounting (LC 123 art. 27) [P&R-SN 11.2]. | ECD waived if a Livro Caixa is kept (Lei 8.981/95 art. 45). | Accountant export |
| **ECD** | — | Waived (IN RFB 2003/2021 art. 3), except an ME/EPP that receives angel investment [P&R-SN 12.5]. | Waived if a Livro Caixa is kept. https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/perguntas-frequentes/sped/ecd/ecd/quem-e-obrigado-a-utilizar | Accountant |
| **ECF** | — | Waived (DEFIS instead). https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/ecf/perguntas-e-respostas-pj-2023.pdf | Required. | Accountant |
| **EFD ICMS/IPI** | — | Waived by Protocolo ICMS 03/11, except states that imposed it by Q1 2014; MG requires it above the sublimit. https://www.confaz.fazenda.gov.br/legislacao/protocolos/2011/pt003_11 · https://portalsped.fazenda.mg.gov.br/spedmg/export/sites/spedmg/efd/downloads/Perguntas-Frequentes-EFD-v.2024.01.pdf | Required for ICMS/IPI taxpayers (Ajuste SINIEF 02/09). https://www.confaz.fazenda.gov.br/legislacao/ajustes/2009/AJ_002_09 | Fiscal, Inventory (Bloco H) |
| **Bloco K** | — | Whether Simples is covered: NF. | Revenue ≥ R$300M: full Bloco K. Revenue ≥ R$78M: K200/K280 from 2018. Other industrials and wholesalers (CNAE 462–469): K200/K280 from 2019. A state may waive wholesalers under R$10M (Ajuste SINIEF 25/16). https://www.confaz.fazenda.gov.br/legislacao/ajustes/2016/aj_025_16 | Production, market-specific |
| **EFD-Contribuições** | — | Waived (IN RFB 1252/2012 art. 5 I). | **Required.** https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/ecf/perguntas-e-respostas-pessoa-juridica-2021-arquivos/capitulo-xxvii-efd-contribuicoes-2021.pdf | Fiscal export, accountant |
| **EFD-Reinf / DCTFWeb** | DCTFWeb if the MEI has an employee or withholds. https://www.gov.br/pt-br/servicos/declarar-debitos-e-creditos-tributarios-federais | Reinf group 3 (IN RFB 2237/2024). https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=141910 · https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/perguntas-frequentes/sped/efd-reinf/efdr | Required. | Accountant (AP withholding data) |
| **Periodic returns** | DASN-SIMEI by the end of May [P&R-MEI 3.9]. | PGDAS-D monthly by the 20th [P&R-SN 6.4]; DEFIS by 31/03 [P&R-SN 6.10]. | (ECF, EFD-C) | Revenue reports per CNAE/annex |
| **SINTEGRA** | MT exempts MEI. https://www.setasc.mt.gov.br/web/sefaz/-/fazenda-notifica-contribuintes-omissos-no-sinteg-1 | Set state by state. MG and ES waive it for EFD filers (https://www.fazenda.mg.gov.br/empresas/ped/duvidas_frequentes/ · https://sefaz.es.gov.br/sintegra); MT keeps it. Current national list: NF. | Same. | Fiscal export, low priority |
| **eSocial** | Only an MEI with its one allowed employee, via the simplified WEB MEI module. https://www.gov.br/esocial/pt-br/microempreendedor-individual/manual-web-mei | Every employer [P&R-SN 11.5]. | Every employer. | Payroll, via accountant |
| **FGTS Digital** | Monthly FGTS via the eSocial DAE. | Mandatory from the 03/2024 pay period. https://www.gov.br/trabalho-e-emprego/pt-br/servicos/empregador/fgtsdigital/perguntas-frequentes | Same. | Payroll, via accountant |

**Stock valuation**
- Permitted: average cost (custo médio) or most-recent cost, which in practice is PEPS/FIFO. With no integrated cost system, arbitrated fallbacks apply (RIR/2018 arts. 301, 306–308; DL 1.598/77 art. 14) [P&R-PJ].
- LIFO is not among the permitted methods; an explicit prohibition was NF.
- Bloco H carries the 31/12 inventory [P&R-PJ Q037].
- **Seed default: custo médio**, with a valuation seam.

**Retention**
- Keep books and documents until prescrição or decadência runs out (RIR/2018 art. 278; CC art. 1.194) [P&R-PJ Q033].
- Practical floor: 5 years from 1 January of the year after the tax event (CTN 173 I; text not verified directly). The seed already has `fiscal_retention.py`.

**Accounting standard**
- NBC TG 1002 covers microentities with revenue up to R$4.8M (CFC). https://www1.cfc.org.br/sisweb/SRE/docs/NBCTG1002.pdf
- NBC TG 1001 covers R$4.8M–R$78M. ITG 1000 (reissued 12/2022) has a model chart of accounts. https://cfc.org.br/wp-content/uploads/2023/01/ITG-1000.pdf

**Tax reform (design-critical)**
- **NF-e/NFC-e fields.** NT 2025.002-RTC adds IBS/CBS/IS groups to NF-e and NFC-e; latest version v1.52 (ATC nº 8, 29/09/2026). https://www.cgibs.gov.br/upload/arquivos/202610/01120217-nfe-nfc-cte-notas-faturas-e-demais-atc-rfb-sufis-cgibs-diretoria-executiva-n-8-de-29-de-setembro-de-2026.pdf
- **Rejection suspended.** Missing IBS/CBS fields no longer cause rejection. https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/julho/receita-federal-e-cgibs-flexibilizarao-obrigatoriedade-de-informacoes-em-documentos-fiscais
- **The duty to fill them stands.** SEFAZ-ES says the legal obligation remains. https://sefaz.es.gov.br/Media/Links/Nota%20IBS%20CBS%20Sefaz.pdf → **fill the fields anyway.**
- **Simples from 01/01/2027.**
  - IBS/CBS obligations, including the fiscal-document fields, start then.
  - Each company can choose to collect IBS/CBS inside or outside the DAS. The choice is made in September or March and takes effect the next semester [P&R-SN 2.27].
  - **The company profile needs an `ibs_cbs_outside_das` setting.**

### B.2 Table-stakes by size

| Module | MEI | Simples ME/EPP | Mid-size / Presumido | Legal driver |
|---|---|---|---|---|
| Customers/suppliers registry (CNPJ/CPF, IE, address) | ✔ | ✔ | ✔ | NF-e recipient data |
| AP/AR + cash flow + Livro Caixa view | ✔ (Relatório Mensal) | ✔ (Livro Caixa, art. 63) | ✔ | Res. 140 arts. 63/106 |
| Bank reconciliation (OFX → Open Finance) | nice | ✔ | ✔ | — |
| DRE / managerial reports | nice | ✔ | ✔ | NBC TG 1002 (via accountant) |
| Cost centres / budgeting | — | nice | ✔ | — |
| Products/services with fiscal data (NCM, CFOP, CEST, origem, unit, service code) | ✔ | ✔ | ✔ | NF-e/NFS-e layouts |
| Quotes → sales orders → invoicing | nice | ✔ | ✔ | — |
| NFS-e Nacional | ✔ (services) | ✔ from 01/11/2026 | ✔ | Res. CGSN 169/191 |
| NF-e | to PJ | ✔ | ✔ | Res. 140 arts. 79/106 |
| NFC-e | rare | ✔ for retail (SP: SAT gone 2026) | ✔ | state law |
| Inventory: locations, movements, custo médio, 31/12 count | goods sellers | ✔ | ✔ + lots/serials | Registro de Inventário / Bloco H |
| Purchasing + NF-e entry XML import | nice | ✔ | ✔ (+ PO approval) | Registro de Entradas |
| Contracts / recurring billing | nice | ✔ (services) | ✔ | — |
| Accountant export (XML bundle, entries layout) | ✔ | ✔ | ✔ | SPED is done by the accountant |
| Permissions + audit | 1 user | ✔ | ✔ | LGPD |
| Multi-company | — | rare | ✔ | — |
| EFD ICMS/IPI / EFD-Contribuições files | — | mostly waived | ✔ (usually accountant-built) | Ajuste 02/09; IN 1252 |
| Payroll / eSocial | via accountant | via accountant | via accountant or Sankhya-class | eSocial |
| Fixed assets / depreciation | — | — | ✔ | — |
| MDF-e / CT-e | — | own delivery / carriers only | same | Ajuste 21/10, 09/07 |

## C. Generic (every market) vs market-specific

- **Generic L1 (every market):**
  - Parties registry
  - Finance (AP/AR, cash, reconciliation, DRE, cost centres, budget)
  - Products/services catalog with fiscal fields
  - Quotes/orders
  - Fiscal adapter (NF-e/NFS-e/NFC-e)
  - Inventory core (locations, ledger, custo médio, count)
  - Purchasing core
  - Contracts/recurring billing
  - Accountant export
  - Dashboards, permissions/audit, multi-company, AI layer
- **Market-specific L2 (seams):**
  - Production/BOM/Bloco K (manufacturing, food, crafts)
  - Service orders / OS (repair shops, field services)
  - Rentals: Odoo ships Rental as a separate app
  - Real estate: we already have `products/erp-imobiliario` and `domain/real_estate`
  - PDV/NFC-e and the till (retail, food)
  - Marketplace hub (e-commerce sellers)
  - CT-e/MDF-e (logistics, own delivery)
  - Lots/expiry/serials (food, pharma, electronics)
  - Projects/timesheets (agencies, consultancies)
  - Payroll (only if a market lacks an accountant)
  - Fixed assets (capital-heavy markets)

## D. Pricing and packaging

| Vendor | Tiers (monthly, BRL as shown 2026-10-14) | What is gated |
|---|---|---|
| **Bling** | Cobalto R$60 · Titânio R$96 promo (list R$120) · Diamante R$357,50 promo (list R$650; the table also shows R$7.800, inconsistent) · Elite from R$1.250 (quote) | **Users:** 5 / 50 / 100 / unlimited.<br>**Marketplace/API orders per month:** 200 → 500–5.000 → 10.000 → custom.<br>**AI credits:** 25 / 60–250 / 500 / 1.000.<br>**Titânio+:** boleto, reconciliation, DRE, dashboards; multi-company (3/5/7 accounts).<br>**Elite:** flexible API.<br>**Every tier:** unlimited invoices.<br>**Extras:** premium support R$150; implementation R$300 per 2h. |
| **Olist ERP** | Avance R$66 · Construa R$177 (promo R$159,30) · Impulsione R$390 (promo R$312) · Domine R$948 (promo R$663,60) · Protagonize (quote) | **Gated by** listing count (2k / 5k / 10k / 20k), API rate (none / 30 / 60 / 120 rpm), AI credits and storage.<br>**Every tier:** unlimited users and orders.<br>**Construa+:** reconciliation, DRE, multi-company (column mapping partly inferred).<br>**Extras:** R$800 minimum fee if GMV is under R$10k; per-Pix/boleto fees; annual plan carries a 10% early-cancellation fine. |
| **Omie** | ERP Padrão from R$309 · Multivarejo from R$419 | **Price scales** by gross-revenue band (≤R$6.750 to R$400k+/month); unlimited users.<br>**Multivarejo adds** e-commerce, marketplaces and PDV.<br>**Omie.Store add-ons:** prices not shown. |
| **Conta Azul** | Essencial R$179,90 (MEI, 1 user) · Controle R$349,90 (ME, 2) · Avançado R$439,90 (EPP, 5) · Performance R$799,90 (>R$1.5M, 15). Lowest of three prices shown; read as annual (inferred). | **Gated by** revenue band and users only. Per-feature gating: NF. |
| **Nibo** | Light R$208 · Plus R$312 · Premium R$479 (monthly; annual R$166 / 250 / 383) | **Plus:** cost centres, permissions, accrual basis.<br>**Premium:** budgeting, batch boleto/NFS-e, CNAB, API.<br>**Every tier:** unlimited users. |
| **Granatum** | Single plan R$396 | Unlimited users; NFS-e on request. |
| **Sankhya** | No public price | — |
| **TOTVS** | Small-business line "a partir de R$74,92" · ERP Cloud from R$1.800 (search snippets) | **PRO plan:** CRM, PDV, production orders, contracts. |
| **Odoo** | One App Free R$0 · Standard R$38,40/user · Custom R$69,10/user (intro prices) | **A 2nd app** forces Standard.<br>**Custom:** Studio, multi-company, external API.<br>**Brazil taxes:** Avalara credits extra. |
| **ERPNext** | Self-host free (GPL-3) · Frappe Cloud from US$5/site/month | Hosting-based, not per user. |

**Packaging lessons**
- Gating levers in this market:
  - Bling: users, orders, AI credits
  - Olist: listings, API rate
  - Omie, Conta Azul: revenue band
  - Nibo: feature tiers
- **Finance depth is the most common upsell:** reconciliation, DRE, cost centres, budgeting.
- AI is already metered as credits (Bling, Olist).

## E. Integrations that matter

**Open Finance**
- Only BCB-authorised institutions participate (Res. Conjunta 1/2020 art. 1). An ERP gets account data through a partnership with an authorised institution, with the client's prior express consent (art. 36). https://normativos.bcb.gov.br/Lists/Normativos/Attachments/51028/Res_Conj_0001_v8_L.pdf
- **Practical path: an aggregator.**
  - Pluggy (BCB-licensed ITP): data plan from R$2.500/month, payments plan from R$500/month. https://www.pluggy.ai/pricing · https://docs.pluggy.ai/docs/open-finance-regulated
  - Belvo: ITP licence; pricing NF. https://belvo.com/blog/belvo-receives-license-to-initiate-payments-in-brazil/
- **Seed shape:** a `BankFeed` Protocol + Fake + Real (Pluggy). OFX stays the zero-cost fallback.

**Pix**
- BCB API Pix spec, v2.10.0. https://github.com/bacen/pix-api
  - Charges: cob (immediate), cobv (with due date), lotecobv (batches)
  - Webhooks
  - Pix Automático: rec / cobr
- **Pix Automático** (Res. BCB 402/2024) has been live since 16/06/2025. https://www.gov.br/fazenda/pt-br/composicao/orgaos/orgaos-colegiados/crsfn/acesso-a-informacao/noticias/2024/bc-aperfeicoa-mecanismos-de-seguranca-do-pix-e-divulga-nova-data-de-lancamento-do-pix-automatico
- **Pix por aproximação / JSR** launched 28/02/2025. https://www.gov.br/secom/pt-br/acompanhe-a-secom/noticias/2025/02/pix-por-aproximacao-comeca-a-funcionar-nesta-sexta-feira-28
- **PSP developer portals:**
  - Inter: https://developers.inter.co/
  - Efí: https://dev.efipay.com.br/
  - Asaas: https://docs.asaas.com/docs/pix-automatico-implementacao (webhooks are at-least-once → idempotent handlers)

**Boleto**
- Registration has been mandatory since the FEBRABAN Nova Plataforma de Cobrança, final phase 10/11/2018. https://portal.febraban.org.br/pagina/3150/1094/pt-br/servicos-novo-plataforma-boletos
- Layouts:
  - CNAB 240 v10.13 and CNAB 750 (Pix): https://portal.febraban.org.br/pagina/3425/33/pt-br/layout-febraban
  - CNAB 400 is bank-specific (no FEBRABAN standard found).
- Hybrid boleto + Pix QR (boleto híbrido), via Inter Bolepix and Efí Bolix APIs.
- **Seed:** keep boleto and Pix inside the existing payments adapter (Asaas already does both). Bank-direct CNAB is an L2/mid-size need.

**Statements**
- OFX: the FDX OFX Work Group. https://financialdataexchange.org/about-fdx/ofx-work-group/
- CNAB 240 statement (segment E), bank-specific, e.g. Itaú: https://download.itau.com.br/bankline/conciliacao_bancaria_%20240.pdf
- The seed finance organ already imports OFX and CSV.

**Card acquirers (EDI)**
- Cielo EDI v15.15 (includes Pix). https://desenvolvedores.cielo.com.br/api-portal/sites/default/files/edi/CIELOEletronicStatement.Manual.version.15.15.pdf
- Rede: EEVD / EEVC / EEFI files. https://www.userede.com.br/n/documentos
- Stone: reconciliation API. https://conciliacao.stone.com.br/
- Matters for retail/PDV markets (L2).

**Accountant software**
- **Domínio "leiaute com separador"** (pipe-delimited). https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=672
  - 0200 = chart of accounts
  - 0220 = accounting histories
  - 0240 = cost centres
  - 0451 = journal entry (debit, credit, amount, history)
  - plus invoice record families
- **Omie's per-system exports:**
  - Domínio: https://ajuda.omie.com.br/pt-BR/articles/9009287-importando-os-lancamentos-contabeis-no-sistema-dominio-leiaute-com-separador
  - Questor: https://ajuda.omie.com.br/pt-BR/articles/9020335-importando-os-lancamentos-contabeis-do-omie-no-sistema-questor-modelo-c
  - Alterdata: https://ajuda.omie.com.br/pt-BR/articles/10715148-importando-os-lancamentos-contabeis-no-sistema-alterdata-leiaute-wcont
  - Contmatic: https://ajuda.omie.com.br/pt-BR/articles/9010782-importando-os-lancamentos-contabeis-no-sistema-contmatic
- **Conta Azul:**
  - Domínio integration: https://ajuda.contaazul.com/hc/pt-br/articles/29271486393869
  - ZIP export (TXT + XML): https://ajuda.contaazul.com/hc/pt-br/articles/44910085481741
- **Nibo:** "Automação Contábil" export for Domínio and 50+ systems; every category needs an accounting code. https://ajuda.nibo.com.br/pt-BR/articles/12733033
- **Bling:** XML ZIP by period. https://ajuda.bling.com.br/hc/pt-br/articles/360035753933
- **Fortes:** NF.
- **NF-e `autXML`:** names the CPF/CNPJ (e.g. the accountant) allowed to download the XML from SEFAZ. https://www.confaz.fazenda.gov.br/legislacao/arquivo-manuais/moc7-anexo-i-leiaute-e-rv.pdf
- **Seed shape:** an `AccountingExport` Protocol, one Real per layout (Domínio first). Categories and accounts carry an accounting-code mapping.

**Marketplaces** (L2, e-commerce)
- Mercado Livre: orders, fiscal information on listings, invoice upload. https://developers.mercadolivre.com.br/pt_br/api-fiscal-faturamento-de-venda
- Amazon SP-API: BR marketplace A2Q3Y263D00KWC. https://developer-docs.amazon.com/sp-api/docs/marketplace-ids
- Magalu: https://developers.magalu.com/
- Shopee: https://open.shopee.com/ (not fetchable; NF)

**Digital certificate**
- NF-e needs an ICP-Brasil A1 or A3 certificate, for both XML signing and TLS. https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=2iHRyFoJDRg%3D (older edition of the manual)
- Focus NFe (already our provider) holds the A1 on the client's behalf; certificate upload and expiry alerts belong in the seed.

## F. Recommended generic ERP seed module list (priority order)

**Coverage legend**
- **Covered:** shipped in `seed/lib/backend/noctusai_lib/domain/{commerce,finance}` or the platform.
- **Partial:** a base exists but needs generalising.
- **New:** nothing exists yet.
- Code checked 2026-10-14. There is no `stock`, `inventory` or `purchase` module in commerce or finance, and `InvoiceKind` = {nfe, nfse} only.

| # | Module | Status | What exists / what's new |
|---|---|---|---|
| 1 | **Company fiscal profile** (CNPJ, IE/IM, regime MEI/SN/LP, CNAE, NFS-e mode, IBS/CBS-outside-DAS, A1 certificate + expiry) | Partial | `commerce/profile.py` + `effective_nfse_mode` + `integrations/cnpj_registry`. New: regime-driven obligations calendar, `ibs_cbs_outside_das`, certificate lifecycle. |
| 2 | **Finance** (AP/AR, accounts, categories, cost centres, cash flow, DRE, OFX/CSV, reconciliation, recurrences, attachments, exports) | Covered | `domain/finance/*` (cost_centers table exists). New: budget vs actual; Livro Caixa / MEI Relatório Mensal report views; accounting-code mapping on categories. |
| 3 | **Parties registry** (customers + suppliers + carriers, CPF/CNPJ/IE, CEP lookup) | Partial | `commerce/customers.py`, `integrations/cnpj_registry`, `integrations/cep`. New: supplier/carrier roles in one party model. |
| 4 | **Products & services catalog with fiscal data** (NCM, CEST, CFOP rules, origem, unit, service list item/cTribNac, IBS/CBS class) | Partial | `commerce/catalog.py` + `fiscal_types`. New: back-office-first catalog, unit conversions, kits. |
| 5 | **Fiscal adapter** (NF-e, NFS-e Nacional, **NFC-e**, cancel/CC-e, XML archive, IBS/CBS fields) | Partial | NF-e + NFS-e via Focus NFe, `fiscal_retention`. New: NFC-e kind, incoming-XML (purchase) import, `autXML` = accountant, IBS/CBS groups. |
| 6 | **Sales: quotes → orders → invoicing** (back-office order entry, price lists, discounts) | Partial | `commerce/orders.py`, `order_state.py` (storefront-origin), coupons. New: quotes/proposals, manual/B2B orders, an `order_source` seam. |
| 7 | **Inventory core** (locations, movement ledger = kardex, reservations, custo médio, 31/12 inventory count → Registro de Inventário/Bloco H data, valuation seam) | **New** | Nothing in seed. Lots/serials/expiry ship as seams for L2. |
| 8 | **Purchasing** (suppliers, POs, receive against NF-e XML, landed cost → custo médio, AP generation) | **New** | Feeds finance AP (`finance/booking.py` Protocol exists). |
| 9 | **Contracts & recurring billing** (contract entity, periodic AR + NFS-e, Pix Automático) | Partial | `finance/recurrences.py`, `payments/subscription.py`, Asaas. New: contract entity + auto-invoice. |
| 10 | **Accountant export & portal** (XML bundle by period, Domínio leiaute first, generic CSV, accountant role read-only) | **New** | `finance/exports.py` is the base. |
| 11 | **Bank feeds / Open Finance** (`BankFeed` Protocol, Fake + Real via aggregator) | **New** | OFX/CSV covered; aggregator costs ≥R$2.500/month, so it is a platform-level contract. |
| 12 | **Dashboards / BI + AI layer** (cash forecast, overdue AR, margin, ABC, NCM/CFOP suggestion, invoice capture) | Partial | `domain/ai`, `digest`, `notifications`; the seed AI framework. |
| 13 | **Permissions, audit, multi-company** | Partial | `domain/permissions`, `action_log.py`, org model. New: one owner over N CNPJs (group view). |
| 14 | **CRM-lite** | Verify | `domain/pipeline` may already be it; check before building. |
| L2 | PDV/NFC-e till + card EDI · production/BOM/Bloco K · service orders · rentals · real estate (exists) · marketplace hub · CT-e/MDF-e · projects/timesheets · payroll · fixed assets | market seams | Do not build in L1. |

### Open questions for the owner

1. **Target regime mix.** MEI + Simples only for v1, or Lucro Presumido too? Presumido adds EFD-Contribuições, EFD ICMS/IPI and ECF data duties.
2. **Inventory scope.** Is the inventory core (#7) in L1? If most early markets sell services, it could be L2. The legal floor for goods sellers is the 31/12 Registro de Inventário.
3. **Open Finance budget.** Accept an aggregator cost (Pluggy from R$2.500/month platform-wide), or stay OFX-only plus the Asaas account statement for v1?
4. **Accountant integration.** Is Domínio-first correct, i.e. does the target accountant base use it? Do we want a white-label accountant portal (Conta Azul Mais / Nibo-style BPO) as a channel?
5. **NFC-e / PDV.** Generic or retail-L2? SP clients lost SAT on 01/01/2026.
6. **Payroll.** Confirm "via accountant only" (all four operational ERPs do this). Do we just export the employee register?
7. **Pricing levers.** Revenue band (Omie/Conta Azul), users (Bling) or feature tiers (Nibo)? Meter AI as credits?
8. **IBS/CBS outside-DAS option.** Ship it as a profile field now? It takes effect from 2027 and the next option window is March 2027.
9. **Multi-company.** Is "one owner, several CNPJs" in v1? Bling, Olist and Odoo all gate it to paid tiers.
10. **First L2 market** to pilot the specialisation: services (OS + contracts), retail (PDV), or manufacturing (BOM)?

**Design takeaways**
- **Same seams as commerce:** `party_role`, `product_type`, `order_source`, `fulfillment_type`, `valuation_method`, `document_kind`.
- **Every IO module ships Protocol + Fake + Real + factory:** fiscal, bank feed, accountant export, PSP.
- **Regime is the master switch.** Tax regime on the company profile drives which documents, books and reports are offered.
- **Build for the 2027 Simples IBS/CBS fields and the 01/11/2026 NFS-e Nacional cut-over now.**
