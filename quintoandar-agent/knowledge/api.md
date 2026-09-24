# Observed API — QuintoAndar partner portal

Captured 2026-09-24 from the browser (in-page fetch/XHR logger + `performance`
resource entries). **Read calls only** — no write action was ever executed, so no write
endpoint is known. Only method, path, parameter NAMES and top-level response keys were
recorded; never values, tokens or personal identifiers.

**Unknown:** how requests are authenticated (cookies vs. headers) — not inspected. Do not
build an off-browser client on assumptions; first inspect auth (with the user's consent)
and record it here.

## Hosts

| Host | Role |
|---|---|
| `listings.quintoandar.com.br` | Next.js app; `/_next/data/<build>/pt-BR/<route>.json` prefetches |
| `apigw.prod.quintoandar.com.br` | Data API gateway (everything below) |
| `event-gateway.quintoandar.com.br/event/batch`, `telemetry-web.shared.quintoandar.com.br/collect`, Sentry, Amplitude, `xp-spec.quintoandar.com.br` (config) | Telemetry/config — not portal data |

Lead pages (`/lead/...`) are server-rendered: **no** client API calls.

## Conventions

`:id` = QA numeric property code · `:uuid` = UUID · `:visitCode` = 8-char visit code.

## Loaded on every page

| Call | Response keys |
|---|---|
| GET `/portfolio-manager-api/user-session/context` | profile, product, companyUuid, personUuid, personName, status |
| GET `/company-api/companies/:uuid/info` | not captured |
| GET `/portfolio-manager-api/member-management/check-person-registration-completeness` | not captured |
| GET `/portfolio-manager-api/feature-management` | not captured |
| GET `/portfolio-manager-api/property-listing/counters` | total, count{} (feeds sidebar badges) |

## Per page

| Page | Call | Param names | Response keys |
|---|---|---|---|
| Início | GET `/portfolio-manager-api/listing-visits/waiting-confirm-visits-count` | — | not captured |
| Início | GET `/portfolio-manager-api/company-management/operation-areas/has-regions` | contextType, personUuid | not captured |
| Início, Visitas | GET `/portfolio-manager-api/listing-visits/list` | pageSize, currentPage, status (repeated), visitType | items[], currentPage, itemsPerPage, totalPages, totalItems, hasNextPage, hasPreviousPage |
| Visit drawers | GET `/portfolio-manager-api/visits/:visitCode/details` | — | agentAllocationOutcome{} |
| Visit drawers | GET `/portfolio-manager-api/visits/:visitCode/entry-access` | — | accessKey, accessModel, accessType, keyHolders[], updatedAt, accessDetails, location, accessCode, trackingLog[], houseDetails{}, entryAccessOptions[] |
| Hours modal (Início) | GET `/portfolio-manager-api/property-details/:id/visit-availability` | country | houseId, availabilityWeekDays{} |
| Status lists | GET `/portfolio-manager-api/property-listing/search` | perPage, page, groupName | not captured |
| Search | GET `/portfolio-manager-api/property-listing/search` | perPage, page, searchTermValue, searchTermType, groupName | not captured |
| Property header | GET `/portfolio-manager-api/property-overview/:id/header` | — | coverImageUrl, formatedAddress, address{}, title, complement, houseType, owner{}, crmId, businessContexts[] |
| Resumo | GET `/portfolio-manager-api/property-overview/:id/summary/price-card` | — | priceBox{}, statusBox{} |
| Resumo | GET `/portfolio-manager-api/property-overview/:id/summary/nudge-card` | — | items[] |
| Resumo, Visitas tab | GET `/portfolio-manager-api/property-overview/:id/entry-access` | — | same as visit entry-access |
| Detalhes | GET `/portfolio-manager-api/property-overview/:id/details` | — | bedroomCount, suitesCount, bathroomCount, isFurnished, parkingSlots, totalArea, hasAfternoonSunlight, hasMorningSunlight, hasQuietStreet, hasOpenView, acceptPets, floor, description, availableItems[], unavailableItems[] |
| Visitas tab | GET `/portfolio-manager-api/property-overview/:id/visit-availability` | country | houseId, availabilityWeekDays{} |
| Desempenho | GET `/portfolio-manager-api/listing-performance/listings` | page, perPage | not captured |
| Minhas propostas | GET `/portfolio-manager-api/listing-sale-offers/in-negotiation` | page, perPage, paymentMethod, orderBy, type | not captured |
| Minhas propostas | GET `/portfolio-manager-api/listing-sale-offers/counter-by-status` | status, type | not captured |
| Performance | GET `/reports-api/last-data-update` | — | not captured |
| Performance | GET `/reports-api/post-publication/weekly/traffic` | range | not captured |
| Gerenciar usuários | GET `/portfolio-manager-api/member-management/members-list` | page, size | not captured |
| Gerenciar usuários | GET `/portfolio-manager-api/member-management/addition-profile-list` | — | not captured |
| Sessões de Fotos | GET `/portfolio-manager-api/listing-photo-session/list` | page, perPage | not captured |

## Enums observed (value ↔ UI)

| Where | Values | UI mapping |
|---|---|---|
| `listing-visits/list` `status` | REQUESTED, CONFIRMED, DONE, CANCELED | Não confirmada / Confirmada / (DONE never shown) / Cancelada — mapping by name, not verified row-by-row |
| `listing-visits/list` `visitType` | MY_SUPPLY, MY_CLIENTS, LEAD_GEN | chips Meus imóveis / Meus clientes / Clientes QuintoAndar (by click order) |
| URL `businessContext` / lead path type | RENT, SALE, HYBRID | Aluguel / Venda / Aluguel e Venda |
| URL `/status/:status` | pending, processing, published, unpublished, notEligible, discarded, all | sidebar items |
| `/photos?status=` | PENDING, SCHEDULED, WAITING_PUBLICATION | Para agendar / Agendadas / Aguardando publicação |
| Sale-offer routes | in-negotiation, ongoing, accepted, tic-created, post-ccv, finished, canceled | Todas / Recebidas / Aceitas / TIC emitida / Assinadas / Concluídas / Canceladas |
| `/operation-areas?contextType=` | COMPANY, AGENT | agency vs. person area |
| `/reports/pos?tab=` | tab label text | Performance tabs |

## How to extend this file

Use `playbook/snippets/api-logger.js` (install after page load; survives in-app clicks,
lost on full reload), perform the action, read `window.__nocLog`. For a write action this
requires the user's explicit consent for that specific action first.
