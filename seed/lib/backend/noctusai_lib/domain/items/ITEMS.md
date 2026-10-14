# Items organ -- fiscal field formats and sources

What the organ validates, where each rule comes from, and what it deliberately does NOT claim.
**Verification status:** the rules below were written from the cited standards as known to the author;
this session had no network access, so no source was re-fetched and no live table was queried.
Anything marked UNVERIFIED must be checked against the official publication before it is relied on
beyond a format check. Nothing here is guessed silently: a rule is either cited or flagged.

| Field | Stored as | Rule enforced | Source | Not enforced / status |
|---|---|---|---|---|
| `ncm` | 8 digits, text | exactly 8 digits after dropping `.` (printed `8471.30.19`); chapter (first 2) 01..97 | Nomenclatura Comum do Mercosul, published by Receita Federal / Siscomex ("Tabela NCM"; TIPI for IPI rates) | Existence of the code in the CURRENT table is UNVERIFIED (table changes by Resolução Gecex; not bundled). Chapter range 01..97 is the Harmonized System range -- confirm before relying on 98/99. |
| `cest` | 7 digits, text | exactly 7 digits after dropping `.` (printed `01.001.00` = segmento 2 + item 3 + especificação 2) | Convênio ICMS 142/2018 (CEST, Anexos I..XXIX by segment) | Existence / the NCM<->CEST pairing is UNVERIFIED (Convênio annexes change; not bundled). Whether a given item REQUIRES a CEST depends on the UF and ST regime -- not decided here. |
| `cfop_default` | 4 digits, text | exactly 4 digits after dropping `.` (printed `5.102`); first digit in 1,2,3 (entrada: UF / outra UF / exterior) or 5,6,7 (saída: idem) | CFOP table, Convênio s/nº de 15/12/1970 and later Ajustes SINIEF (current list in the SPED/NF-e technical notes) | Existence of the 4-digit code in the current table is UNVERIFIED. It is a DEFAULT suggestion -- the operation's real CFOP is decided per document by the (future) invoicing organ. |
| `origem` | smallint 0..8 | integer 0..8 | Tabela "Origem da Mercadoria" (campo `orig` of the NF-e layout; Ajuste SINIEF 20/2012 introduced the 3,5,6,7,8 values; 0=nacional ... 8=nacional, importação > 70%) | Stored as the bare digit. The pt-BR labels shown by the frontend organ (`items/messages.ts`, `origem.*`) follow the NF-e layout manual's table as recalled by the author -- UNVERIFIED this session; check against the current MOC before relying on the wording. |
| `gtin` | 8/12/13/14 digits, text | digits only (dash tolerated), length in {8,12,13,14}, GS1 mod-10 check digit correct (weights 3,1,3,1 from the right over the body) | GS1 General Specifications, "Check digit calculation" (GTIN-8/12/13/14) | Whether the GTIN is ISSUED / registered to this company (GS1 Brasil Cadastro Nacional de Produtos) is UNVERIFIABLE offline. The DB CHECK covers length only; the check digit is validated by the service. |
| `unit` | text enum | UN, KG, G, L, ML, M, M2, M3, H, CX, PCT | Common NF-e `uCom` abbreviations. The NF-e layout leaves `uCom` free text (1..6 chars) -- this list is the organ's own pragmatic set, not an official closed list. | Add units by extending the enum + CHECK (a contract change). |
| `cost_cents` | bigint >= 0 | non-negative integer cents | -- | INFORMATIONAL: becomes derived (moving-average cost) when the inventory organ lands; until then it is whatever the operator typed. |
| `price_cents` | bigint >= 0, nullable | non-negative integer cents | -- | A REFERENCE price only; the sales price lives on the commerce offer. |

## `item_type` -- vertical-seed seam

Seed values: `goods`, `service`, `raw_material`, `asset` (Python enum `ItemType` + SQL CHECK).
A vertical adds values through `ItemsConfig(extra_item_types=("procedure",))`: they join the
CHECK, the service validation and the OpenAPI-visible error message. Seed values are never removed or
renamed by config. Downstream organs (inventory) decide per type whether stock applies -- `service`
items normally carry none.

## Other decisions

- SKU is stored UPPER-CASED: uniqueness is per org and case-insensitive by construction (also a unique
  index on `lower(sku)`).
- Items are archived (`is_active=false`), never deleted: inventory / purchasing / commerce will hold FKs.
- A category reference cannot cross tenants even if the service were bypassed: composite
  `FOREIGN KEY (org_id, category_id)` on `UNIQUE (org_id, id)`.
- CSV round-trips (`export.csv` -> edit -> `import`): see `csv_io.py` for the exact column set and the
  validate-everything-first / blank-cell-keeps-value semantics.
- Commerce link: `commerce_products.item_id` (nullable FK) lands in W3 -- NOC-REMEDIATE[items-commerce-link]
  (see `sql.py`), roadmap E5.
